/**
 * transmissionService.ts
 *
 * Mock transmission service — replace method implementations with real
 * REST/WebSocket calls to the Python backend when ready.
 *
 * Backend integration points:
 *   transmitPayload  → POST /api/transmit
 *   cancelTransmission → POST /api/transmit/cancel
 *   getActivityLog   → GET /api/activity  (or WebSocket stream)
 */

import type {
  Transmission,
  TransmissionConfig,
  TransmissionStatus,
  ActivityEvent,
} from '../types';

const generateId = () =>
  `WP-${String(Math.floor(Math.random() * 900) + 100).padStart(3, '0')}`;

const now = () => {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
};

// Simulated transmission stages
const STAGES: { status: TransmissionStatus; label: string; duration: number }[] = [
  { status: 'encrypting', label: 'ENCRYPTING PAYLOAD', duration: 1200 },
  { status: 'encoding', label: 'ENCODING ERROR CORRECTION', duration: 1000 },
  { status: 'modulating', label: 'MODULATING SIGNAL', duration: 900 },
  { status: 'transmitting', label: 'TRANSMITTING ACOUSTIC DATA', duration: 2000 },
];

export type TransmissionProgressCallback = (
  status: TransmissionStatus,
  progress: number,
  label: string
) => void;

/**
 * Simulate transmitting a payload through the acoustic channel.
 * Returns the completed Transmission object.
 */
export async function transmitPayload(
  payload: string,
  config: TransmissionConfig,
  onProgress?: TransmissionProgressCallback
): Promise<Transmission> {
  const id = generateId();
  const startedAt = new Date();

  let cumulativeProgress = 0;
  const stageWeight = 100 / STAGES.length;

  for (const stage of STAGES) {
    const stepsInStage = 10;
    const stepDuration = stage.duration / stepsInStage;

    for (let i = 0; i <= stepsInStage; i++) {
      await delay(stepDuration);
      const stageProgress = (i / stepsInStage) * stageWeight;
      const totalProgress = Math.min(
        Math.round(cumulativeProgress + stageProgress),
        100
      );
      onProgress?.(stage.status, totalProgress, stage.label);
    }

    cumulativeProgress += stageWeight;
  }

  onProgress?.('complete', 100, 'TRANSMISSION COMPLETE');

  const transmission: Transmission = {
    id,
    payload,
    payloadSize: new TextEncoder().encode(payload).length,
    frequency: config.frequency,
    symbolDuration: config.symbolDuration,
    mode: config.mode,
    status: 'complete',
    progress: 100,
    startedAt,
    completedAt: new Date(),
  };

  return transmission;
}

/**
 * Cancel an in-progress transmission.
 * Backend: POST /api/transmit/cancel
 */
export async function cancelTransmission(_id: string): Promise<void> {
  await delay(200);
}

/**
 * Get live activity log events.
 * Backend: GET /api/activity or subscribe to WebSocket stream.
 */
export function getActivityLog(): ActivityEvent[] {
  const base = new Date();
  const events: ActivityEvent[] = [
    {
      id: '1',
      timestamp: formatTime(new Date(base.getTime() - 14000)),
      event: 'CHANNEL INITIALIZED',
      level: 'info',
    },
    {
      id: '2',
      timestamp: formatTime(new Date(base.getTime() - 11000)),
      event: 'PAYLOAD ENCRYPTED',
      level: 'success',
    },
    {
      id: '3',
      timestamp: formatTime(new Date(base.getTime() - 9000)),
      event: 'ECC FRAME GENERATED',
      level: 'success',
    },
    {
      id: '4',
      timestamp: formatTime(new Date(base.getTime() - 6000)),
      event: 'AFSK MODULATION READY',
      level: 'info',
    },
    {
      id: '5',
      timestamp: formatTime(new Date(base.getTime() - 4000)),
      event: 'TRANSMISSION STARTED',
      level: 'success',
    },
    {
      id: '6',
      timestamp: formatTime(new Date(base.getTime() - 2000)),
      event: '64% PAYLOAD TRANSMITTED',
      level: 'info',
    },
  ];
  return events;
}

/**
 * Generate a new live activity event (called periodically by components).
 */
export function generateLiveEvent(): ActivityEvent {
  const events = [
    { event: 'CHANNEL HEARTBEAT OK', level: 'info' as const },
    { event: 'SIGNAL INTEGRITY VERIFIED', level: 'success' as const },
    { event: 'ECC FRAME VALIDATED', level: 'success' as const },
    { event: 'NOISE FLOOR STABLE', level: 'info' as const },
    { event: 'KEY ROTATION DEFERRED', level: 'warning' as const },
    { event: 'PACKET 0x4F ACKNOWLEDGED', level: 'success' as const },
    { event: 'FREQUENCY LOCK MAINTAINED', level: 'info' as const },
    { event: 'PAYLOAD FRAGMENT SENT', level: 'info' as const },
  ];

  const pick = events[Math.floor(Math.random() * events.length)];
  return {
    id: String(Date.now()),
    timestamp: now(),
    event: pick.event,
    level: pick.level,
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function delay(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

function formatTime(d: Date) {
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
}

export { now };
