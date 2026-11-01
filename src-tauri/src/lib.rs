pub mod sidecar;

use sidecar::PythonBridge;
use std::sync::Arc;
use tauri::{command, Manager, State};

struct AppState {
    bridge: Arc<PythonBridge>,
}

#[command]
async fn get_app_status(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    state
        .bridge
        .send_command("get_app_status", serde_json::json!({}), 5)
        .await
}

#[command]
async fn list_audio_devices(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    state
        .bridge
        .send_command("list_audio_devices", serde_json::json!({}), 10)
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
        .send_command("run_calibration", params, 15)
        .await
}

#[command]
async fn start_engine(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    state
        .bridge
        .send_command("start_engine", serde_json::json!({}), 5)
        .await
}

#[command]
async fn stop_engine(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    state
        .bridge
        .send_command("stop_engine", serde_json::json!({}), 5)
        .await
}

#[command]
async fn shutdown_engine(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    state
        .bridge
        .send_command("shutdown_engine", serde_json::json!({}), 5)
        .await
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
            get_app_status,
            list_audio_devices,
            run_calibration,
            start_engine,
            stop_engine,
            shutdown_engine,
        ])
        .run(tauri::generate_context!())
        .expect("error while building tauri application");
}
