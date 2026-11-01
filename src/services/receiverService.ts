/**
 * receiverService.ts
 *
 * Mock receiver service — replace with WebSocket stream from Python backend.
 *
 * Backend integration points:
 *   startReceiver  → POST /api/receiver/start (then subscribe to WebSocket)
 *   stopReceiver   → POST /api/receiver/stop
 *   getSignalStatus → GET /api/receiver/status
 */

import type { Receiver, ReceiverStatus } from '../types';

export type ReceiverProgressCallback = (receiver: Receiver) => void;

const DECODED_SAMPLES = [
  'OPERATION NIGHTFALL — PHASE 2 AUTHORIZED',
  'RENDEZVOUS COORDINATES: 48.8566° N, 2.3522° E',
  'AUTHENTICATION TOKEN: 7f4a2b9c-e1d3-4f8a-b2c7-9e5d1a3f6b2c',
  'NETWORK BRIDGE OFFLINE — USE ACOUSTIC RELAY',
  'SECURE HANDSHAKE COMPLETE. PROCEED WITH TRANSFER.',
];

/**
 * Simulate starting the acoustic receiver.
 * Backend: POST /api/receiver/start → WebSocket at ws://localhost:8765/receiver
 */
export async function startReceiver(
  onUpdate: ReceiverProgressCallback,
  signal?: AbortSignal
): Promise<void> {
  const stages: { status: ReceiverStatus; delay: number; receiver: Partial<Receiver> }[] = [
    {
      status: 'listening',
      delay: 800,
      receiver: { status: 'listening', isLocked: false },
    },
    {
      status: 'signal_detected',
      delay: 1800,
      receiver: {
        status: 'signal_detected',
        detectedFrequency: 19.002,
        snr: 31.6,
        isLocked: false,
      },
    },
    {
      status: 'locked',
      delay: 1200,
      receiver: {
        status: 'locked',
        detectedFrequency: 19.002,
        snr: 31.6,
        isLocked: true,
      },
    },
    {
      status: 'decoding',
      delay: 2000,
      receiver: {
        status: 'decoding',
        detectedFrequency: 19.002,
        snr: 31.6,
        isLocked: true,
      },
    },
    {
      status: 'complete',
      delay: 500,
      receiver: {
        status: 'complete',
        detectedFrequency: 19.002,
        snr: 31.6,
        isLocked: true,
        decodedPayload: DECODED_SAMPLES[Math.floor(Math.random() * DECODED_SAMPLES.length)],
        payloadSize: Math.floor(Math.random() * 900) + 200,
        integrity: 99.9 + Math.random() * 0.1,
      },
    },
  ];

  for (const stage of stages) {
    if (signal?.aborted) return;
    await delay(stage.delay);
    if (signal?.aborted) return;
    onUpdate(stage.receiver as Receiver);
  }
}

/**
 * Stop the receiver.
 * Backend: POST /api/receiver/stop
 */
export async function stopReceiver(): Promise<void> {
  await delay(100);
}

/**
 * Get current signal status.
 * Backend: GET /api/receiver/status
 */
export async function getSignalStatus(): Promise<Receiver> {
  await delay(50);
  return {
    status: 'idle',
    isLocked: false,
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function delay(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}
