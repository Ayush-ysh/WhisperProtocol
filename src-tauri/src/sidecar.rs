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
        let python_bin = Self::find_python_interpreter()?;
        let backend_dir = Self::find_backend_dir()?;

        log::info!(
            "Spawning Python engine sidecar: {:?} in {:?}",
            python_bin,
            backend_dir
        );

        let mut child: Child = Command::new(&python_bin)
            .arg("-m")
            .arg("whisper.engine.bridge")
            .current_dir(&backend_dir)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| format!("Failed to spawn Python process: {e}"))?;

        let pid = child.id().unwrap_or(0);
        let stdin = child.stdin.take().ok_or("Failed to capture child stdin")?;
        let stdout = child.stdout.take().ok_or("Failed to capture child stdout")?;
        let stderr = child.stderr.take().ok_or("Failed to capture child stderr")?;

        let pending: Arc<Mutex<HashMap<String, ResponseSender>>> =
            Arc::new(Mutex::new(HashMap::new()));
        let is_running = Arc::new(AtomicBool::new(true));

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

    fn find_python_interpreter() -> Result<PathBuf, String> {
        if let Ok(env_path) = std::env::var("WHISPER_PYTHON_BIN") {
            let p = PathBuf::from(env_path);
            if p.exists() {
                return Ok(p);
            }
        }

        // Try workspace venv (during development)
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let venv_python = manifest_dir
            .parent()
            .unwrap_or(&manifest_dir)
            .join("backend")
            .join("venv")
            .join("bin")
            .join("python");

        if venv_python.exists() {
            return Ok(venv_python);
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
