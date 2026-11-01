/**
 * securityService.ts
 *
 * Mock security service — replace with real API calls to Python backend.
 *
 * Backend integration points:
 *   getSecurityStatus → GET /api/security/status
 *   getSecurityEvents → GET /api/security/events
 *   generateKey       → POST /api/security/keygen
 */

import type { SecurityStatus, SecurityEvent } from '../types';

/**
 * Get current security status.
 * Backend: GET /api/security/status
 */
export async function getSecurityStatus(): Promise<SecurityStatus> {
  await delay(120);
  return {
    score: 98,
    encryptionAlgorithm: 'AES-256',
    encryptionActive: true,
    errorCorrection: 'Reed-Solomon',
    errorCorrectionActive: true,
    networkExposure: 0,
    rfExposure: 'NONE',
    sessionIntegrity: 100,
    channelAuthenticated: true,
  };
}

/**
 * Get security event timeline.
 * Backend: GET /api/security/events
 */
export async function getSecurityEvents(): Promise<SecurityEvent[]> {
  await delay(80);
  const base = Date.now();
  return [
    {
      id: 'se-1',
      timestamp: new Date(base - 32000),
      event: 'ENCRYPTION KEY GENERATED',
      level: 'success',
    },
    {
      id: 'se-2',
      timestamp: new Date(base - 28000),
      event: 'CHANNEL AUTHENTICATED',
      level: 'success',
    },
    {
      id: 'se-3',
      timestamp: new Date(base - 21000),
      event: 'PAYLOAD SIGNATURE VERIFIED',
      level: 'success',
    },
    {
      id: 'se-4',
      timestamp: new Date(base - 14000),
      event: 'ECC FRAME VALIDATED',
      level: 'success',
    },
    {
      id: 'se-5',
      timestamp: new Date(base - 7000),
      event: 'NOISE FLOOR WITHIN THRESHOLD',
      level: 'info',
    },
    {
      id: 'se-6',
      timestamp: new Date(base - 1000),
      event: 'SESSION INTEGRITY CONFIRMED',
      level: 'success',
    },
  ];
}

/**
 * Generate a new encryption key.
 * Backend: POST /api/security/keygen
 */
export async function generateKey(): Promise<{ keyId: string; algorithm: string }> {
  await delay(600);
  const hex = Array.from({ length: 16 }, () =>
    Math.floor(Math.random() * 256)
      .toString(16)
      .padStart(2, '0')
  ).join('');
  return {
    keyId: hex.slice(0, 8) + '-' + hex.slice(8, 12) + '-' + hex.slice(12, 16),
    algorithm: 'AES-256',
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function delay(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}
