/**
 * Typed API client for the Pictr backend.
 *
 * All requests use fetch() with JSON. Non-2xx responses throw an Error whose
 * message is the backend's `detail` string — ready to display in the UI.
 *
 * Base URL is read from the VITE_API_BASE_URL env var so it works in any env:
 *   VITE_API_BASE_URL=http://localhost:8000  (default)
 */

import type { Brief, Session } from "./types";

const BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:8000";

// ---------------------------------------------------------------------------
// Internal helper
// ---------------------------------------------------------------------------

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // body wasn't JSON — use the status text
    }
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export const api = {
  /** Create a new session in INTAKE phase. */
  createSession: (): Promise<Session> =>
    request<Session>("/session", { method: "POST" }),

  /** Fetch current session state. */
  getSession: (sessionId: string): Promise<Session> =>
    request<Session>(`/session/${sessionId}`),

  /**
   * Submit the creative brief. Transitions session INTAKE → STORYBOARD.
   * Returns the updated session with draft Shot list populated.
   */
  submitBrief: (sessionId: string, brief: Brief): Promise<Session> =>
    request<Session>(`/session/${sessionId}/message`, {
      method: "POST",
      body: JSON.stringify(brief),
    }),

  /**
   * Generate the current shot card. `shotIndex` must equal
   * `session.current_shot_index` — backend enforces the gate.
   */
  generateShot: (sessionId: string, shotIndex: number): Promise<Session> =>
    request<Session>(`/session/${sessionId}/shots/${shotIndex}/generate`, {
      method: "POST",
    }),

  /** Approve the shot and advance to the next. */
  approveShot: (sessionId: string, shotIndex: number): Promise<Session> =>
    request<Session>(`/session/${sessionId}/shots/${shotIndex}/approve`, {
      method: "POST",
    }),

  /** Attach revision feedback and mark shot for regeneration. */
  reviseShot: (
    sessionId: string,
    shotIndex: number,
    feedback: string,
  ): Promise<Session> =>
    request<Session>(`/session/${sessionId}/shots/${shotIndex}/revise`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    }),
};
