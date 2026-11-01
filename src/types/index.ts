// ─── Transmission ───────────────────────────────────────────────────────────

export type TransmissionStatus =
  | 'idle'
  | 'encrypting'
  | 'encoding'
  | 'modulating'
  | 'transmitting'
  | 'complete'
  | 'error';

export type TransmissionMode = 'direct' | 'broadcast';

export interface Transmission {
  id: string;
  payload: string;
  payloadSize: number;
  frequency: number;
  symbolDuration: number;
  mode: TransmissionMode;
  status: TransmissionStatus;
  progress: number;
  startedAt?: Date;
  completedAt?: Date;
  errorMessage?: string;
}

export interface TransmissionConfig {
  frequency: number;
  symbolDuration: number;
  errorCorrection: string;
  mode: TransmissionMode;
}

// ─── Receiver ────────────────────────────────────────────────────────────────

export type ReceiverStatus =
  | 'idle'
  | 'listening'
  | 'signal_detected'
  | 'locked'
  | 'decoding'
  | 'complete';

export interface Receiver {
  status: ReceiverStatus;
  detectedFrequency?: number;
  snr?: number;
  isLocked: boolean;
  decodedPayload?: string;
  payloadSize?: number;
  integrity?: number;
}

// ─── Security ────────────────────────────────────────────────────────────────

export interface SecurityStatus {
  score: number;
  encryptionAlgorithm: string;
  encryptionActive: boolean;
  errorCorrection: string;
  errorCorrectionActive: boolean;
  networkExposure: number;
  rfExposure: string;
  sessionIntegrity: number;
  channelAuthenticated: boolean;
}

export type SecurityEventLevel = 'info' | 'success' | 'warning' | 'danger';

export interface SecurityEvent {
  id: string;
  timestamp: Date;
  event: string;
  level: SecurityEventLevel;
}

// ─── Diagnostics ─────────────────────────────────────────────────────────────

export type DiagnosticStatus = 'pass' | 'fail' | 'running' | 'pending';

export interface DiagnosticResult {
  component: string;
  status: DiagnosticStatus;
  value?: string;
  message?: string;
}

export interface DeviceInfo {
  audioInput: string;
  audioInputAvailable: boolean;
  audioOutput: string;
  audioOutputAvailable: boolean;
  sampleRate: number;
  channelBand: string;
  latency: number;
  noiseLevel: number;
}

// ─── Sessions ────────────────────────────────────────────────────────────────

export type SessionDirection = 'TX' | 'RX';
export type SessionStatus = 'complete' | 'failed' | 'active';

export interface Session {
  id: string;
  direction: SessionDirection;
  payloadSize: string;
  duration: string;
  integrity: number;
  status: SessionStatus;
  timestamp: Date;
  frequency: number;
  mode: TransmissionMode;
}

// ─── Audio Channel ────────────────────────────────────────────────────────────

export interface AudioChannel {
  centerFrequency: number;
  minFrequency: number;
  maxFrequency: number;
  signalStrength: number;
  noiseFloor: number;
  sampleRate: number;
  latency: number;
  isActive: boolean;
}

// ─── Broadcast ───────────────────────────────────────────────────────────────

export type BroadcastNodeStatus = 'connected' | 'synced' | 'disconnected' | 'error';

export interface BroadcastNode {
  id: string;
  label: string;
  status: BroadcastNodeStatus;
  signal: number;
  integrity: string;
  latency: number;
}

// ─── Activity ────────────────────────────────────────────────────────────────

export type ActivityLevel = 'info' | 'success' | 'warning' | 'danger';

export interface ActivityEvent {
  id: string;
  timestamp: string;
  event: string;
  level: ActivityLevel;
}

// ─── Command Palette ──────────────────────────────────────────────────────────

export interface CommandItem {
  id: string;
  label: string;
  description: string;
  icon: string;
  route: string;
  shortcut?: string;
}
