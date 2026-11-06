/**
 * Type-safe Tauri IPC client for WhisperProtocol.
 *
 * Connects the React presentation layer to the Tauri 2 Rust desktop host
 * which supervises the Python DSP core engine over stdin/stdout JSON Lines.
 */

export interface FrequencyProfile {
  name: string;
  freq_zero: number;
  freq_one: number;
  symbol_duration: number;
  baud: number;
}

export interface AppStatus {
  engine_state: 'ready' | 'idle' | 'stopped';
  version: string;
  protocol_version: number;
  platform: string;
  default_sample_rate: number;
  supported_sample_rates: number[];
  receiver_mode?: boolean;
  discovering?: boolean;
  local_alias?: string;
  profile?: string;
  profiles: {
    primary: FrequencyProfile;
    secondary: FrequencyProfile;
  };
  audio_hardware: {
    default_input: string | null;
    default_output: string | null;
  };
}

export interface AudioDeviceEntry {
  index: number;
  name: string;
  channels: number;
  default_sample_rate: number;
  hostapi: string;
  supports_44100: boolean;
  supports_48000: boolean;
}

export interface AudioDeviceList {
  inputs: AudioDeviceEntry[];
  outputs: AudioDeviceEntry[];
  default_input_index: number | null;
  default_output_index: number | null;
}

export interface BandMetric {
  detected: boolean;
  peak_frequency: number;
  peak_magnitude: number;
  snr_db: number | null;
}

export interface CalibrationResult {
  input_device_index: number | null;
  output_device_index: number | null;
  sample_rate: number;
  noise_floor_db: number;
  band_18khz: BandMetric;
  band_19khz: BandMetric;
  channel_ready: boolean;
}

export interface DiscoveredPeer {
  alias: string;
  session_id: number;
  last_seen: number;
  age_seconds: number;
  rssi_db: number;
  profile: string;
}

export interface TransferSessionInfo {
  session_id: number;
  role: 'sender' | 'receiver';
  state: string;
  file_name: string;
  file_size: number;
  peer_alias: string;
  sas_code: string | null;
  error_message: string | null;
  ecc_symbols: number;
  profile_name: string;
  created_at: number;
  payload_received?: boolean;
}

export interface BroadcastStatusInfo {
  session_id: number;
  file_name: string;
  file_size: number;
  state: string;
  profile_name: string;
  ecc_symbols: number;
  nodes: Record<string, {
    alias: string;
    slot_index: number;
    slot_delay_seconds: number;
    status: string;
    last_updated: number;
  }>;
  delivery_count: number;
  total_nodes: number;
  created_at: number;
}

export interface TransferHistoryEntry {
  id: number;
  session_id: number;
  direction: 'tx' | 'rx';
  peer_alias: string;
  file_name: string;
  file_size: number;
  status: 'completed' | 'declined' | 'failed';
  sas_code: string | null;
  error_message: string | null;
  created_at: number;
  completed_at: number | null;
}

export function isTauriEnvironment(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

/**
 * Invoke a Tauri command safely, with fallback if running outside Tauri.
 */
async function invokeTauri<T>(cmd: string, args: Record<string, unknown> = {}): Promise<T> {
  if (isTauriEnvironment()) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      return await invoke<T>(cmd, args);
    } catch (e) {
      console.error(`[Tauri IPC] Error invoking ${cmd}:`, e);
      throw e;
    }
  }

  // Graceful fallback for web development preview (when running npm run dev in standard browser)
  console.warn(`[Tauri IPC] '${cmd}' invoked outside Tauri desktop container. Using local fallback.`);
  return getWebFallbackResponse<T>(cmd, args);
}

// ─── Core & Diagnostics ─────────────────────────────────────────────────────

export async function checkMicrophonePermission(): Promise<'authorized' | 'denied' | 'restricted' | 'not_determined'> {
  return invokeTauri<'authorized' | 'denied' | 'restricted' | 'not_determined'>('check_microphone_permission');
}

export async function requestMicrophonePermission(): Promise<'authorized' | 'denied' | 'restricted' | 'not_determined'> {
  return invokeTauri<'authorized' | 'denied' | 'restricted' | 'not_determined'>('request_microphone_permission');
}

export async function getAppStatus(): Promise<AppStatus> {
  return invokeTauri<AppStatus>('get_app_status');
}

export async function listAudioDevices(): Promise<AudioDeviceList> {
  return invokeTauri<AudioDeviceList>('list_audio_devices');
}

export async function runCalibration(options?: {
  inputDeviceIndex?: number;
  outputDeviceIndex?: number;
  sampleRate?: number;
}): Promise<CalibrationResult> {
  return invokeTauri<CalibrationResult>('run_calibration', {
    inputDeviceIndex: options?.inputDeviceIndex ?? null,
    outputDeviceIndex: options?.outputDeviceIndex ?? null,
    sampleRate: options?.sampleRate ?? 48000,
  });
}

export async function startEngine(): Promise<boolean> {
  const res = await invokeTauri<{ started: boolean }>('start_engine');
  return res.started;
}

export async function stopEngine(): Promise<boolean> {
  const res = await invokeTauri<{ stopped: boolean }>('stop_engine');
  return res.stopped;
}

export async function shutdownEngine(): Promise<boolean> {
  const res = await invokeTauri<{ shutdown: boolean }>('shutdown_engine');
  return res.shutdown;
}

// ─── Discovery ──────────────────────────────────────────────────────────────

export async function setReceiverMode(enabled: boolean, alias?: string, profile?: string): Promise<{ receiver_mode: boolean; alias: string }> {
  return invokeTauri<{ receiver_mode: boolean; alias: string }>('set_receiver_mode', { enabled, alias: alias ?? null, profile: profile ?? null });
}

export async function startDiscovery(alias?: string, profile?: string): Promise<{ discovering: boolean; alias: string }> {
  return invokeTauri<{ discovering: boolean; alias: string }>('start_discovery', { alias: alias ?? null, profile: profile ?? null });
}

export async function stopDiscovery(): Promise<{ discovering: boolean }> {
  return invokeTauri<{ discovering: boolean }>('stop_discovery');
}

export async function getDiscoveredDevices(): Promise<{ devices: DiscoveredPeer[] }> {
  return invokeTauri<{ devices: DiscoveredPeer[] }>('get_discovered_devices');
}

// ─── Transfer ───────────────────────────────────────────────────────────────

export async function sendTransferOffer(params: {
  fileName: string;
  payloadText?: string;
  payloadBase64?: string;
  targetAlias?: string;
  profile?: string;
  ecc?: number;
}): Promise<{ session_id: number; file_name: string; file_size: number }> {
  return invokeTauri<{ session_id: number; file_name: string; file_size: number }>('send_transfer_offer', {
    fileName: params.fileName,
    payloadText: params.payloadText ?? null,
    payloadBase64: params.payloadBase64 ?? null,
    targetAlias: params.targetAlias ?? null,
    profile: params.profile ?? 'ultrasonic',
    ecc: params.ecc ?? 8,
  });
}

export async function acceptTransfer(sessionId: number): Promise<{ session_id: number; accepted: boolean }> {
  return invokeTauri<{ session_id: number; accepted: boolean }>('accept_transfer', { sessionId });
}

export async function declineTransfer(sessionId: number, reason?: string): Promise<{ session_id: number; declined: boolean }> {
  return invokeTauri<{ session_id: number; declined: boolean }>('decline_transfer', { sessionId, reason: reason ?? null });
}

export async function confirmSas(sessionId: number, confirmed: boolean): Promise<{ session_id: number; sas_confirmed: boolean; success: boolean }> {
  return invokeTauri<{ session_id: number; sas_confirmed: boolean; success: boolean }>('confirm_sas', { sessionId, confirmed });
}

export async function getTransferStatus(sessionId: number): Promise<{ session_id: number; status: TransferSessionInfo | null }> {
  return invokeTauri<{ session_id: number; status: TransferSessionInfo | null }>('get_transfer_status', { sessionId });
}

// ─── Broadcast ──────────────────────────────────────────────────────────────

export async function sendBroadcast(params: {
  fileName: string;
  payloadText?: string;
  payloadBase64?: string;
  targets: string[];
  profile?: string;
  ecc?: number;
}): Promise<{ session_id: number; targets: string[]; file_name: string; file_size: number }> {
  return invokeTauri<{ session_id: number; targets: string[]; file_name: string; file_size: number }>('send_broadcast', {
    fileName: params.fileName,
    payloadText: params.payloadText ?? null,
    payloadBase64: params.payloadBase64 ?? null,
    targets: params.targets,
    profile: params.profile ?? 'ultrasonic',
    ecc: params.ecc ?? 8,
  });
}

export async function getBroadcastStatus(sessionId: number): Promise<{ session_id: number; status: BroadcastStatusInfo | null }> {
  return invokeTauri<{ session_id: number; status: BroadcastStatusInfo | null }>('get_broadcast_status', { sessionId });
}

// ─── Settings & Storage ────────────────────────────────────────────────────

export async function getSettings(): Promise<{ settings: Record<string, string> }> {
  return invokeTauri<{ settings: Record<string, string> }>('get_settings');
}

export async function updateSetting(key: string, value: string): Promise<{ updated: boolean; key: string; value: string }> {
  return invokeTauri<{ updated: boolean; key: string; value: string }>('update_setting', { key, value });
}

export async function getSavedNodes(): Promise<{ nodes: DiscoveredPeer[] }> {
  return invokeTauri<{ nodes: DiscoveredPeer[] }>('get_saved_nodes');
}

export async function deleteSavedNode(alias: string): Promise<{ deleted: boolean }> {
  return invokeTauri<{ deleted: boolean }>('delete_saved_node', { alias });
}

export async function getTransferHistory(limit = 50): Promise<{ history: TransferHistoryEntry[] }> {
  return invokeTauri<{ history: TransferHistoryEntry[] }>('get_transfer_history', { limit });
}

export async function clearTransferHistory(): Promise<{ cleared: boolean }> {
  return invokeTauri<{ cleared: boolean }>('clear_transfer_history');
}

// ─── Event Bus Listening ───────────────────────────────────────────────────

export async function listenToEngineEvent<T>(
  eventName: string,
  callback: (data: T) => void
): Promise<() => void> {
  if (isTauriEnvironment()) {
    const { listen } = await import('@tauri-apps/api/event');
    const unlisten = await listen<T>(`whisper:${eventName}`, (event) => {
      callback(event.payload);
    });
    return unlisten;
  }
  return () => {};
}

/**
 * Web fallback responses used only when running preview in normal browser without Tauri host.
 */
function getWebFallbackResponse<T>(cmd: string, args: Record<string, unknown>): T {
  if (cmd === 'get_app_status') {
    return {
      engine_state: 'idle',
      version: '0.1.0-web-preview',
      protocol_version: 1,
      platform: 'browser',
      default_sample_rate: 48000,
      supported_sample_rates: [44100, 48000],
      receiver_mode: false,
      discovering: false,
      profiles: {
        primary: {
          name: 'ultrasonic_standard',
          freq_zero: 18000,
          freq_one: 19000,
          symbol_duration: 0.02,
          baud: 50,
        },
        secondary: {
          name: 'acoustic_audible_fallback',
          freq_zero: 14000,
          freq_one: 15000,
          symbol_duration: 0.02,
          baud: 50,
        },
      },
      audio_hardware: {
        default_input: 'Browser WebAudio Input',
        default_output: 'Browser WebAudio Output',
      },
    } as unknown as T;
  }

  if (cmd === 'check_microphone_permission' || cmd === 'request_microphone_permission') {
    return 'authorized' as unknown as T;
  }

  if (cmd === 'list_audio_devices') {
    return {
      inputs: [
        {
          index: 0,
          name: 'WebAudio Virtual Microphone',
          channels: 1,
          default_sample_rate: 48000,
          hostapi: 'CoreAudio',
          supports_44100: true,
          supports_48000: true,
        },
      ],
      outputs: [
        {
          index: 1,
          name: 'WebAudio Virtual Speakers',
          channels: 2,
          default_sample_rate: 48000,
          hostapi: 'CoreAudio',
          supports_44100: true,
          supports_48000: true,
        },
      ],
      default_input_index: 0,
      default_output_index: 1,
    } as unknown as T;
  }

  if (cmd === 'run_calibration') {
    return {
      input_device_index: 0,
      output_device_index: 1,
      sample_rate: 48000,
      noise_floor_db: -54.2,
      band_18khz: {
        detected: false,
        peak_frequency: 18000,
        peak_magnitude: 0.002,
        snr_db: 4.1,
      },
      band_19khz: {
        detected: false,
        peak_frequency: 19000,
        peak_magnitude: 0.001,
        snr_db: 3.8,
      },
      channel_ready: true,
    } as unknown as T;
  }

  if (cmd === 'get_discovered_devices' || cmd === 'get_saved_nodes') {
    return {
      devices: [
        { alias: 'Workstation Alpha', session_id: 0x1234, last_seen: Date.now(), age_seconds: 4, rssi_db: 24.5, profile: 'ultrasonic' },
        { alias: 'Field Unit Beta', session_id: 0x5678, last_seen: Date.now(), age_seconds: 12, rssi_db: 18.2, profile: 'audible' },
      ],
      nodes: [
        { alias: 'Workstation Alpha', session_id: 0x1234, last_seen: Date.now(), age_seconds: 4, rssi_db: 24.5, profile: 'ultrasonic' },
      ],
    } as unknown as T;
  }

  if (cmd === 'get_settings') {
    return {
      settings: {
        alias: 'WhisperLocal',
        profile: 'ultrasonic',
        sample_rate: '48000',
        ecc_symbols: '8',
        auto_calibrate: 'true',
      },
    } as unknown as T;
  }

  if (cmd === 'get_transfer_history') {
    return {
      history: [
        {
          id: 1,
          session_id: 0xCAFEBABE,
          direction: 'rx',
          peer_alias: 'Field Unit Beta',
          file_name: 'coordinates.txt',
          file_size: 48,
          status: 'completed',
          sas_code: '842-195',
          error_message: null,
          created_at: Date.now() / 1000 - 300,
          completed_at: Date.now() / 1000 - 290,
        },
      ],
    } as unknown as T;
  }

  if (cmd === 'send_transfer_offer' || cmd === 'send_broadcast') {
    return {
      session_id: Math.floor(Math.random() * 1000000),
      file_name: (args.fileName as string) || 'message.txt',
      file_size: 64,
      targets: (args.targets as string[]) || [],
    } as unknown as T;
  }

  return { success: true, updated: true, cleared: true, deleted: true } as unknown as T;
}
