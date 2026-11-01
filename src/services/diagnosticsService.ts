/**
 * diagnosticsService.ts
 *
 * Mock diagnostics service — replace with real API calls to Python backend.
 *
 * Backend integration points:
 *   runDiagnostics → POST /api/diagnostics/run
 *   getDeviceInfo  → GET  /api/diagnostics/device
 */

import type { DiagnosticResult, DiagnosticStatus, DeviceInfo } from '../types';

export type DiagnosticProgressCallback = (result: DiagnosticResult) => void;

const COMPONENTS = [
  { component: 'MICROPHONE', value: 'Input Level OK' },
  { component: 'SPEAKER', value: 'Output Level OK' },
  { component: 'FREQUENCY', value: '19.0 kHz Nominal' },
  { component: 'SIGNAL', value: 'SNR 31.6 dB' },
  { component: 'CHANNEL', value: '18–20 kHz Active' },
];

/**
 * Run full channel diagnostic suite.
 * Backend: POST /api/diagnostics/run → returns streamed results
 */
export async function runDiagnostics(
  onResult: DiagnosticProgressCallback
): Promise<DiagnosticResult[]> {
  const results: DiagnosticResult[] = [];

  for (const comp of COMPONENTS) {
    // Mark as running
    onResult({ component: comp.component, status: 'running' });
    await delay(600 + Math.random() * 400);

    const status: DiagnosticStatus = Math.random() > 0.05 ? 'pass' : 'fail';
    const result: DiagnosticResult = {
      component: comp.component,
      status,
      value: comp.value,
      message: status === 'pass' ? 'PASS' : 'CHECK HARDWARE',
    };
    results.push(result);
    onResult(result);
  }

  return results;
}

/**
 * Get device info.
 * Backend: GET /api/diagnostics/device
 */
export async function getDeviceInfo(): Promise<DeviceInfo> {
  await delay(100);
  return {
    audioInput: 'Microphone',
    audioInputAvailable: true,
    audioOutput: 'Speaker',
    audioOutputAvailable: true,
    sampleRate: 44100,
    channelBand: '18–20 kHz',
    latency: 12,
    noiseLevel: -42,
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function delay(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}
