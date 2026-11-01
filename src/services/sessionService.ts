/**
 * sessionService.ts
 *
 * Mock session service — replace with real API calls to Python backend.
 *
 * Backend integration points:
 *   getSessions   → GET /api/sessions
 *   getSession    → GET /api/sessions/:id
 */

import type { Session } from '../types';

const MOCK_SESSIONS: Session[] = [
  {
    id: 'WP-001',
    direction: 'TX',
    payloadSize: '2.4 KB',
    duration: '3.2s',
    integrity: 100,
    status: 'complete',
    timestamp: new Date(Date.now() - 1000 * 60 * 3),
    frequency: 19.0,
    mode: 'direct',
  },
  {
    id: 'WP-002',
    direction: 'RX',
    payloadSize: '850 B',
    duration: '1.8s',
    integrity: 99.9,
    status: 'complete',
    timestamp: new Date(Date.now() - 1000 * 60 * 7),
    frequency: 18.5,
    mode: 'direct',
  },
  {
    id: 'WP-003',
    direction: 'TX',
    payloadSize: '6.1 KB',
    duration: '7.4s',
    integrity: 100,
    status: 'complete',
    timestamp: new Date(Date.now() - 1000 * 60 * 12),
    frequency: 19.0,
    mode: 'broadcast',
  },
  {
    id: 'WP-004',
    direction: 'RX',
    payloadSize: '1.2 KB',
    duration: '2.1s',
    integrity: 98.7,
    status: 'complete',
    timestamp: new Date(Date.now() - 1000 * 60 * 18),
    frequency: 20.0,
    mode: 'direct',
  },
  {
    id: 'WP-005',
    direction: 'TX',
    payloadSize: '512 B',
    duration: '0.9s',
    integrity: 100,
    status: 'complete',
    timestamp: new Date(Date.now() - 1000 * 60 * 25),
    frequency: 19.0,
    mode: 'direct',
  },
  {
    id: 'WP-006',
    direction: 'RX',
    payloadSize: '3.7 KB',
    duration: '4.5s',
    integrity: 99.4,
    status: 'complete',
    timestamp: new Date(Date.now() - 1000 * 60 * 31),
    frequency: 18.5,
    mode: 'direct',
  },
  {
    id: 'WP-007',
    direction: 'TX',
    payloadSize: '8.9 KB',
    duration: '10.2s',
    integrity: 100,
    status: 'complete',
    timestamp: new Date(Date.now() - 1000 * 60 * 40),
    frequency: 19.0,
    mode: 'broadcast',
  },
  {
    id: 'WP-008',
    direction: 'RX',
    payloadSize: '256 B',
    duration: '0.5s',
    integrity: 100,
    status: 'complete',
    timestamp: new Date(Date.now() - 1000 * 60 * 52),
    frequency: 19.0,
    mode: 'direct',
  },
];

/**
 * Get all sessions with optional filtering.
 * Backend: GET /api/sessions?direction=TX&status=complete
 */
export async function getSessions(filters?: {
  direction?: 'TX' | 'RX';
  status?: string;
  query?: string;
}): Promise<Session[]> {
  await delay(150);

  let sessions = [...MOCK_SESSIONS];

  if (filters?.direction) {
    sessions = sessions.filter((s) => s.direction === filters.direction);
  }

  if (filters?.status && filters.status !== 'all') {
    sessions = sessions.filter((s) => s.status === filters.status);
  }

  if (filters?.query) {
    const q = filters.query.toLowerCase();
    sessions = sessions.filter(
      (s) =>
        s.id.toLowerCase().includes(q) ||
        s.direction.toLowerCase().includes(q) ||
        s.payloadSize.toLowerCase().includes(q)
    );
  }

  return sessions;
}

/**
 * Get a single session by ID.
 * Backend: GET /api/sessions/:id
 */
export async function getSession(id: string): Promise<Session | undefined> {
  await delay(80);
  return MOCK_SESSIONS.find((s) => s.id === id);
}

/**
 * Add a new session to the log (called after successful transmission/reception).
 * Backend: POST /api/sessions
 */
export function addSession(session: Session): void {
  MOCK_SESSIONS.unshift(session);
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function delay(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}
