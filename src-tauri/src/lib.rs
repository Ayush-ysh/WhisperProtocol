pub mod sidecar;

use sidecar::PythonBridge;
use std::sync::Arc;
use tauri::{command, Manager, State};

struct AppState {
    bridge: Arc<PythonBridge>,
}

#[cfg(target_os = "macos")]
unsafe extern "C" {
    fn mac_check_microphone_permission() -> i32;
    fn mac_request_microphone_permission() -> i32;
}

// ─── Native Hardware & Permission Commands ──────────────────────────────────

#[command]
async fn check_microphone_permission() -> Result<String, String> {
    #[cfg(target_os = "macos")]
    {
        let status = unsafe { mac_check_microphone_permission() };
        match status {
            3 => Ok("authorized".to_string()),
            2 => Ok("denied".to_string()),
            1 => Ok("restricted".to_string()),
            _ => Ok("not_determined".to_string()),
        }
    }
    #[cfg(not(target_os = "macos"))]
    {
        Ok("authorized".to_string())
    }
}

#[command]
async fn request_microphone_permission() -> Result<String, String> {
    #[cfg(target_os = "macos")]
    {
        let status = tokio::task::spawn_blocking(|| unsafe { mac_request_microphone_permission() })
            .await
            .map_err(|e| format!("Failed to request microphone permission: {e}"))?;
        match status {
            3 => Ok("authorized".to_string()),
            2 => Ok("denied".to_string()),
            1 => Ok("restricted".to_string()),
            _ => Ok("not_determined".to_string()),
        }
    }
    #[cfg(not(target_os = "macos"))]
    {
        Ok("authorized".to_string())
    }
}

// ─── Diagnostics & System Commands ──────────────────────────────────────────

#[command]
async fn get_app_status(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    state
        .bridge
        .send_command("get_app_status", serde_json::json!({}), 25)
        .await
}

#[command]
async fn list_audio_devices(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    state
        .bridge
        .send_command("list_audio_devices", serde_json::json!({}), 25)
        .await
}

#[command]
async fn run_calibration(
    state: State<'_, AppState>,
    input_device_index: Option<i32>,
    output_device_index: Option<i32>,
    sample_rate: Option<u32>,
) -> Result<serde_json::Value, String> {
    let params = serde_json::json!({
        "input_device_index": input_device_index,
        "output_device_index": output_device_index,
        "sample_rate": sample_rate.unwrap_or(48000),
    });
    state
        .bridge
        .send_command("run_calibration", params, 30)
        .await
}

#[command]
async fn start_engine(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    state
        .bridge
        .send_command("start_engine", serde_json::json!({}), 25)
        .await
}

#[command]
async fn stop_engine(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    state
        .bridge
        .send_command("stop_engine", serde_json::json!({}), 25)
        .await
}

#[command]
async fn shutdown_engine(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    state
        .bridge
        .send_command("shutdown_engine", serde_json::json!({}), 10)
        .await
}

// ─── Discovery Commands ─────────────────────────────────────────────────────

#[command]
async fn set_receiver_mode(
    state: State<'_, AppState>,
    enabled: bool,
    alias: Option<String>,
    profile: Option<String>,
) -> Result<serde_json::Value, String> {
    let params = serde_json::json!({ "enabled": enabled, "alias": alias, "profile": profile });
    state.bridge.send_command("set_receiver_mode", params, 25).await
}

#[command]
async fn start_discovery(
    state: State<'_, AppState>,
    alias: Option<String>,
    profile: Option<String>,
) -> Result<serde_json::Value, String> {
    let params = serde_json::json!({ "alias": alias, "profile": profile });
    state.bridge.send_command("start_discovery", params, 25).await
}

#[command]
async fn stop_discovery(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    state.bridge.send_command("stop_discovery", serde_json::json!({}), 10).await
}

#[command]
async fn get_discovered_devices(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    state.bridge.send_command("get_discovered_devices", serde_json::json!({}), 10).await
}

// ─── Transfer Commands ──────────────────────────────────────────────────────

#[command]
async fn send_transfer_offer(
    state: State<'_, AppState>,
    file_name: String,
    payload_text: Option<String>,
    payload_base64: Option<String>,
    target_alias: Option<String>,
    profile: Option<String>,
    ecc: Option<u32>,
) -> Result<serde_json::Value, String> {
    let params = serde_json::json!({
        "file_name": file_name,
        "payload_text": payload_text,
        "payload_base64": payload_base64,
        "target_alias": target_alias,
        "profile": profile,
        "ecc": ecc.unwrap_or(8),
    });
    state.bridge.send_command("send_transfer_offer", params, 25).await
}

#[command]
async fn accept_transfer(
    state: State<'_, AppState>,
    session_id: u32,
) -> Result<serde_json::Value, String> {
    let params = serde_json::json!({ "session_id": session_id });
    state.bridge.send_command("accept_transfer", params, 25).await
}

#[command]
async fn decline_transfer(
    state: State<'_, AppState>,
    session_id: u32,
    reason: Option<String>,
) -> Result<serde_json::Value, String> {
    let params = serde_json::json!({ "session_id": session_id, "reason": reason });
    state.bridge.send_command("decline_transfer", params, 10).await
}

#[command]
async fn confirm_sas(
    state: State<'_, AppState>,
    session_id: u32,
    confirmed: bool,
) -> Result<serde_json::Value, String> {
    let params = serde_json::json!({ "session_id": session_id, "confirmed": confirmed });
    state.bridge.send_command("confirm_sas", params, 25).await
}

#[command]
async fn get_transfer_status(
    state: State<'_, AppState>,
    session_id: u32,
) -> Result<serde_json::Value, String> {
    let params = serde_json::json!({ "session_id": session_id });
    state.bridge.send_command("get_transfer_status", params, 10).await
}

// ─── Multi-Device Broadcast Commands ────────────────────────────────────────

#[command]
async fn send_broadcast(
    state: State<'_, AppState>,
    file_name: String,
    payload_text: Option<String>,
    payload_base64: Option<String>,
    targets: Vec<String>,
    profile: Option<String>,
    ecc: Option<u32>,
) -> Result<serde_json::Value, String> {
    let params = serde_json::json!({
        "file_name": file_name,
        "payload_text": payload_text,
        "payload_base64": payload_base64,
        "targets": targets,
        "profile": profile,
        "ecc": ecc.unwrap_or(8),
    });
    state.bridge.send_command("send_broadcast", params, 30).await
}

#[command]
async fn get_broadcast_status(
    state: State<'_, AppState>,
    session_id: u32,
) -> Result<serde_json::Value, String> {
    let params = serde_json::json!({ "session_id": session_id });
    state.bridge.send_command("get_broadcast_status", params, 10).await
}

// ─── Settings & Storage Commands ────────────────────────────────────────────

#[command]
async fn get_settings(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    state.bridge.send_command("get_settings", serde_json::json!({}), 10).await
}

#[command]
async fn update_setting(
    state: State<'_, AppState>,
    key: String,
    value: String,
) -> Result<serde_json::Value, String> {
    let params = serde_json::json!({ "key": key, "value": value });
    state.bridge.send_command("update_setting", params, 10).await
}

#[command]
async fn get_saved_nodes(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    state.bridge.send_command("get_saved_nodes", serde_json::json!({}), 10).await
}

#[command]
async fn delete_saved_node(
    state: State<'_, AppState>,
    alias: String,
) -> Result<serde_json::Value, String> {
    let params = serde_json::json!({ "alias": alias });
    state.bridge.send_command("delete_saved_node", params, 10).await
}

#[command]
async fn get_transfer_history(
    state: State<'_, AppState>,
    limit: Option<u32>,
) -> Result<serde_json::Value, String> {
    let params = serde_json::json!({ "limit": limit.unwrap_or(50) });
    state.bridge.send_command("get_transfer_history", params, 10).await
}

#[command]
async fn clear_transfer_history(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    state.bridge.send_command("clear_transfer_history", serde_json::json!({}), 10).await
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // On macOS, trigger system microphone permission prompt on launch if not yet determined
            #[cfg(target_os = "macos")]
            {
                std::thread::spawn(|| {
                    let _ = unsafe { mac_request_microphone_permission() };
                });
            }

            let app_handle = app.handle().clone();
            tauri::async_runtime::block_on(async move {
                match PythonBridge::spawn(app_handle.clone()).await {
                    Ok(bridge) => {
                        log::info!("Python bridge initialized with PID: {}", bridge.pid());
                        app_handle.manage(AppState { bridge });
                    }
                    Err(e) => {
                        log::error!("CRITICAL: Failed to spawn Python sidecar: {}", e);
                    }
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            check_microphone_permission,
            request_microphone_permission,
            get_app_status,
            list_audio_devices,
            run_calibration,
            start_engine,
            stop_engine,
            shutdown_engine,
            set_receiver_mode,
            start_discovery,
            stop_discovery,
            get_discovered_devices,
            send_transfer_offer,
            accept_transfer,
            decline_transfer,
            confirm_sas,
            get_transfer_status,
            send_broadcast,
            get_broadcast_status,
            get_settings,
            update_setting,
            get_saved_nodes,
            delete_saved_node,
            get_transfer_history,
            clear_transfer_history,
        ])
        .run(tauri::generate_context!())
        .expect("error while building tauri application");
}
