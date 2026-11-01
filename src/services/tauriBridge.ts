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
function getWebFallbackResponse<T>(cmd: string, _args: Record<string, unknown>): T {
  if (cmd === 'get_app_status') {
    return {
      engine_state: 'idle',
      version: '0.1.0-web-preview',
      protocol_version: 1,
      platform: 'browser',
      default_sample_rate: 48000,
      supported_sample_rates: [44100, 48000],
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

  return {} as T;
}
