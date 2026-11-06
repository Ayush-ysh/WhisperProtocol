use std::collections::HashMap;
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tauri::{AppHandle, Emitter};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, Command};
use tokio::sync::{oneshot, Mutex};
use uuid::Uuid;

type ResponseSender = oneshot::Sender<Result<serde_json::Value, String>>;

pub struct PythonBridge {
    stdin: Arc<Mutex<ChildStdin>>,
    pending: Arc<Mutex<HashMap<String, ResponseSender>>>,
    is_running: Arc<AtomicBool>,
    child_pid: u32,
}

impl PythonBridge {
    pub async fn spawn(app_handle: AppHandle) -> Result<Arc<Self>, String> {
        let prefer_python = cfg!(debug_assertions)
            || std::env::var("WHISPER_FORCE_PYTHON").is_ok()
            || std::env::var("WHISPER_PYTHON_BIN").is_ok();

        let mut cmd = if !prefer_python && Self::find_standalone_binary().is_some() {
            let bin = Self::find_standalone_binary().unwrap();
            log::info!("Spawning standalone whisper-engine binary: {:?}", bin);
            Command::new(bin)
        } else {
            let python_bin = Self::find_python_interpreter()?;
            let backend_dir = Self::find_backend_dir()?;
            log::info!(
                "Spawning Python engine sidecar via interpreter: {:?} in {:?}",
                python_bin,
                backend_dir
            );
            let mut c = Command::new(&python_bin);
            c.arg("-m")
                .arg("whisper.engine.bridge")
                .current_dir(&backend_dir);
            c
        };

        let mut child: Child = cmd
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| format!("Failed to spawn engine process: {e}"))?;

        let pid = child.id().unwrap_or(0);
        let stdin = child.stdin.take().ok_or("Failed to capture child stdin")?;
        let stdout = child.stdout.take().ok_or("Failed to capture child stdout")?;
        let stderr = child.stderr.take().ok_or("Failed to capture child stderr")?;

        let pending: Arc<Mutex<HashMap<String, ResponseSender>>> =
            Arc::new(Mutex::new(HashMap::new()));
        let is_running = Arc::new(AtomicBool::new(true));

        let (ready_tx, ready_rx) = oneshot::channel::<()>();
        let ready_tx = Arc::new(Mutex::new(Some(ready_tx)));
        let ready_tx_clone = Arc::clone(&ready_tx);

        // Reader task for stdout (JSON Lines IPC)
        let pending_clone = Arc::clone(&pending);
        let is_running_clone = Arc::clone(&is_running);
        let app_handle_clone = app_handle.clone();

        tokio::spawn(async move {
            let mut reader = BufReader::new(stdout).lines();
            while let Ok(Some(line)) = reader.next_line().await {
                let trimmed = line.trim();
                if trimmed.is_empty() {
                    continue;
                }

                if let Ok(val) = serde_json::from_str::<serde_json::Value>(trimmed) {
                    if let Some(id) = val.get("id").and_then(|i| i.as_str()) {
                        let mut map = pending_clone.lock().await;
                        if let Some(tx) = map.remove(id) {
                            let status = val.get("status").and_then(|s| s.as_str()).unwrap_or("error");
                            if status == "ok" {
                                let data = val.get("data").cloned().unwrap_or(serde_json::Value::Null);
                                let _ = tx.send(Ok(data));
                            } else {
                                let err = val
                                    .get("error")
                                    .and_then(|e| e.as_str())
                                    .unwrap_or("Unknown engine error");
                                let _ = tx.send(Err(err.to_string()));
                            }
                        }
                    } else if let Some(event) = val.get("event").and_then(|e| e.as_str()) {
                        let data = val.get("data").cloned().unwrap_or(serde_json::Value::Null);
                        log::info!("Python bridge event: {} -> {:?}", event, data);
                        if event == "engine.ready" {
                            let mut r = ready_tx_clone.lock().await;
                            if let Some(tx) = r.take() {
                                let _ = tx.send(());
                            }
                        }
                        let _ = app_handle_clone.emit(&format!("whisper:{event}"), data);
                    }
                } else {
                    log::warn!("Invalid JSON from Python stdout: {}", trimmed);
                }
            }
            is_running_clone.store(false, Ordering::SeqCst);
            log::info!("Python bridge stdout closed");
        });

        // Reader task for stderr (Diagnostic logs only)
        tokio::spawn(async move {
            let mut reader = BufReader::new(stderr).lines();
            while let Ok(Some(line)) = reader.next_line().await {
                eprintln!("[python-engine] {line}");
            }
        });

        // Monitor child exit
        let is_running_exit = Arc::clone(&is_running);
        tokio::spawn(async move {
            let status = child.wait().await;
            is_running_exit.store(false, Ordering::SeqCst);
            log::info!("Python process exited with status: {:?}", status);
        });

        // Wait for engine.ready with 45s timeout to accommodate PyInstaller first-run library extraction
        log::info!("Waiting for Python engine.ready signal (up to 45s)...");
        match tokio::time::timeout(Duration::from_secs(45), ready_rx).await {
            Ok(Ok(_)) => {
                log::info!("Python engine successfully initialized and ready!");
            }
            Ok(Err(_)) => {
                log::warn!("Engine ready channel closed unexpectedly, proceeding with bridge");
            }
            Err(_) => {
                log::warn!("Timed out waiting 45s for engine.ready, proceeding with bridge anyway");
            }
        }

        Ok(Arc::new(Self {
            stdin: Arc::new(Mutex::new(stdin)),
            pending,
            is_running,
            child_pid: pid,
        }))
    }

    pub async fn send_command(
        &self,
        cmd: &str,
        params: serde_json::Value,
        timeout_secs: u64,
    ) -> Result<serde_json::Value, String> {
        if !self.is_running.load(Ordering::SeqCst) {
            return Err("Python engine is not running".to_string());
        }

        let req_id = format!("req-{}", Uuid::new_v4());
        let (tx, rx) = oneshot::channel();

        {
            let mut map = self.pending.lock().await;
            map.insert(req_id.clone(), tx);
        }

        let payload = serde_json::json!({
            "id": req_id,
            "cmd": cmd,
            "params": params,
        });

        let mut line = serde_json::to_string(&payload)
            .map_err(|e| format!("Failed to serialize command: {e}"))?;
        line.push('\n');

        {
            let mut stdin = self.stdin.lock().await;
            stdin
                .write_all(line.as_bytes())
                .await
                .map_err(|e| format!("Failed to write to Python stdin: {e}"))?;
            stdin
                .flush()
                .await
                .map_err(|e| format!("Failed to flush Python stdin: {e}"))?;
        }

        match tokio::time::timeout(Duration::from_secs(timeout_secs), rx).await {
            Ok(Ok(res)) => res,
            Ok(Err(_)) => Err("Engine response channel dropped".to_string()),
            Err(_) => {
                let mut map = self.pending.lock().await;
                map.remove(&req_id);
                Err(format!("Command '{cmd}' timed out after {timeout_secs}s"))
            }
        }
    }

    pub fn pid(&self) -> u32 {
        self.child_pid
    }

    pub fn is_alive(&self) -> bool {
        self.is_running.load(Ordering::SeqCst)
    }

    fn find_standalone_binary() -> Option<PathBuf> {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));

        #[cfg(all(target_os = "macos", target_arch = "aarch64"))]
        let triple = "aarch64-apple-darwin";
        #[cfg(all(target_os = "macos", target_arch = "x86_64"))]
        let triple = "x86_64-apple-darwin";
        #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
        let triple = "x86_64-unknown-linux-gnu";
        #[cfg(all(target_os = "windows", target_arch = "x86_64"))]
        let triple = "x86_64-pc-windows-msvc";

        #[cfg(not(any(
            all(target_os = "macos", target_arch = "aarch64"),
            all(target_os = "macos", target_arch = "x86_64"),
            all(target_os = "linux", target_arch = "x86_64"),
            all(target_os = "windows", target_arch = "x86_64")
        )))]
        let triple = "unknown";

        let bin_ext = if cfg!(windows) { ".exe" } else { "" };
        let triple_name = format!("whisper-engine-{triple}{bin_ext}");
        let plain_name = format!("whisper-engine{bin_ext}");

        // 1. Check binaries/ in manifest dir
        let p1 = manifest_dir.join("binaries").join(&triple_name);
        if p1.exists() {
            return Some(p1);
        }
        let p2 = manifest_dir.join("binaries").join(&plain_name);
        if p2.exists() {
            return Some(p2);
        }

        // 2. Check backend/dist/
        if let Some(parent) = manifest_dir.parent() {
            let p3 = parent.join("backend").join("dist").join(&plain_name);
            if p3.exists() {
                return Some(p3);
            }
        }

        // 3. Check alongside current executable (in app bundle or target)
        if let Ok(cur_exe) = std::env::current_exe() {
            if let Some(exe_dir) = cur_exe.parent() {
                let p4 = exe_dir.join(&plain_name);
                if p4.exists() {
                    return Some(p4);
                }
                let p5 = exe_dir.join(&triple_name);
                if p5.exists() {
                    return Some(p5);
                }
            }
        }

        None
    }

    fn find_python_interpreter() -> Result<PathBuf, String> {
        if let Ok(env_path) = std::env::var("WHISPER_PYTHON_BIN") {
            let p = PathBuf::from(env_path);
            if p.exists() {
                return Ok(p);
            }
        }

        // Try workspace venv (during development across macOS, Linux, Windows)
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let venv_dir = manifest_dir
            .parent()
            .unwrap_or(&manifest_dir)
            .join("backend")
            .join("venv");

        let candidates = [
            venv_dir.join("bin").join("python"),
            venv_dir.join("bin").join("python3"),
            venv_dir.join("Scripts").join("python.exe"),
            venv_dir.join("python.exe"),
        ];

        for cand in candidates {
            if cand.exists() {
                return Ok(cand);
            }
        }

        // Fallback to system python3
        which::which("python3")
            .or_else(|_| which::which("python"))
            .map_err(|_| "Could not find Python interpreter in venv or PATH".to_string())
    }

    fn find_backend_dir() -> Result<PathBuf, String> {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let backend_dir = manifest_dir
            .parent()
            .unwrap_or(&manifest_dir)
            .join("backend");

        if backend_dir.exists() {
            Ok(backend_dir)
        } else {
            Err(format!("Backend directory not found at {:?}", backend_dir))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_find_python_interpreter() {
        let py = PythonBridge::find_python_interpreter();
        assert!(py.is_ok(), "Python interpreter should be found in venv or system: {:?}", py);
        assert!(py.unwrap().exists());
    }

    #[test]
    fn test_find_backend_dir() {
        let dir = PythonBridge::find_backend_dir();
        assert!(dir.is_ok(), "Backend directory should exist: {:?}", dir);
        assert!(dir.unwrap().join("whisper").exists());
    }

    #[test]
    fn test_find_standalone_binary() {
        let bin = PythonBridge::find_standalone_binary();
        assert!(bin.is_some(), "Standalone whisper-engine binary should be located in binaries/ or backend/dist/");
        assert!(bin.unwrap().exists());
    }
}

