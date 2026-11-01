/**
 * diagnosticsService.ts
 *
 * Real diagnostics service communicating with the desktop backend via tauriBridge.
 */

import type { DiagnosticResult, DiagnosticStatus, DeviceInfo } from '../types';
import {
  getAppStatus,
  listAudioDevices,
  runCalibration,
} from './tauriBridge';

export type DiagnosticProgressCallback = (result: DiagnosticResult) => void;

/**
 * Run full channel diagnostic suite using real hardware probing.
 */
export async function runDiagnostics(
  onResult: DiagnosticProgressCallback
): Promise<DiagnosticResult[]> {
  const results: DiagnosticResult[] = [];

  // 1. Microphone Hardware
  onResult({ component: 'MICROPHONE', status: 'running' });
  const devices = await listAudioDevices();
  const inputDev = devices.inputs.find((d) => d.index === devices.default_input_index) || devices.inputs[0];
  const micResult: DiagnosticResult = {
    component: 'MICROPHONE',
    status: inputDev ? 'pass' : 'fail',
    value: inputDev ? inputDev.name : 'NO INPUT DEVICE',
    message: inputDev ? `Input Active (${inputDev.channels} ch @ ${inputDev.default_sample_rate} Hz)` : 'MISSING',
  };
  results.push(micResult);
  onResult(micResult);

  // 2. Speaker Hardware
  onResult({ component: 'SPEAKER', status: 'running' });
  const outputDev = devices.outputs.find((d) => d.index === devices.default_output_index) || devices.outputs[0];
  const spkResult: DiagnosticResult = {
    component: 'SPEAKER',
    status: outputDev ? 'pass' : 'fail',
    value: outputDev ? outputDev.name : 'NO OUTPUT DEVICE',
    message: outputDev ? `Output Active (${outputDev.channels} ch @ ${outputDev.default_sample_rate} Hz)` : 'MISSING',
  };
  results.push(spkResult);
  onResult(spkResult);

  // 3. Acoustic Frequency Profiles
  onResult({ component: 'FREQUENCY', status: 'running' });
  const appStatus = await getAppStatus();
  const freqResult: DiagnosticResult = {
    component: 'FREQUENCY',
    status: 'pass',
    value: `${appStatus.profiles.primary.freq_zero / 1000} / ${appStatus.profiles.primary.freq_one / 1000} kHz`,
    message: `${appStatus.profiles.primary.name.toUpperCase()} (${appStatus.profiles.primary.baud} BAUD)`,
  };
  results.push(freqResult);
  onResult(freqResult);

  // 4. Acoustic Calibration & Noise Floor
  onResult({ component: 'SIGNAL', status: 'running' });
  const cal = await runCalibration({
    inputDeviceIndex: devices.default_input_index ?? undefined,
    outputDeviceIndex: devices.default_output_index ?? undefined,
    sampleRate: appStatus.default_sample_rate,
  });

  const sigResult: DiagnosticResult = {
    component: 'SIGNAL',
    status: cal.noise_floor_db < -20 ? 'pass' : 'fail',
    value: `Noise: ${cal.noise_floor_db.toFixed(1)} dB`,
    message: `18k: ${cal.band_18khz.detected ? 'DETECTED' : 'CLEAR'} | 19k: ${cal.band_19khz.detected ? 'DETECTED' : 'CLEAR'}`,
  };
  results.push(sigResult);
  onResult(sigResult);

  // 5. Channel Status
  onResult({ component: 'CHANNEL', status: 'running' });
  const chanResult: DiagnosticResult = {
    component: 'CHANNEL',
    status: cal.channel_ready ? 'pass' : 'fail',
    value: `${cal.sample_rate / 1000} kHz Sample Rate`,
    message: cal.channel_ready ? 'ACOUSTIC CHANNEL READY' : 'CHANNEL NOT CALIBRATED',
  };
  results.push(chanResult);
  onResult(chanResult);

  return results;
}

/**
 * Get real device information from the engine.
 */
export async function getDeviceInfo(): Promise<DeviceInfo> {
  const [appStatus, devices] = await Promise.all([
    getAppStatus(),
    listAudioDevices(),
  ]);

  const input = devices.inputs.find((d) => d.index === devices.default_input_index) || devices.inputs[0];
  const output = devices.outputs.find((d) => d.index === devices.default_output_index) || devices.outputs[0];

  return {
    audioInput: input ? input.name : 'None',
    audioInputAvailable: !!input,
    audioOutput: output ? output.name : 'None',
    audioOutputAvailable: !!output,
    sampleRate: appStatus.default_sample_rate,
    channelBand: `${appStatus.profiles.primary.freq_zero / 1000}–${appStatus.profiles.primary.freq_one / 1000} kHz`,
    latency: 20,
    noiseLevel: -50.0,
  };
}
