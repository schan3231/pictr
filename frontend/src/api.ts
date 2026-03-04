/**
 * Typed API client for the Pictr backend.
 *
 * All requests use fetch() with JSON. Non-2xx responses throw an Error whose
 * message is the backend's `detail` string — ready to display in the UI.
 *
 * Special case: HTTP 503 (LLM upstream unavailable) always returns the message
 * "Planner temporarily unavailable. Please try again." so users see a friendly
 * message regardless of which specific LLM error occurred.
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
    // 503 = upstream LLM unavailable — always show a user-friendly message.
    if (res.status === 503) {
      throw new Error("Planner temporarily unavailable. Please try again.");
    }
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
   * Submit the creative brief. Transitions session INTAKE → PLANNING.
   * Returns the updated session with an initial AI planner message.
   */
  submitBrief: (sessionId: string, brief: Brief): Promise<Session> =>
    request<Session>(`/session/${sessionId}/message`, {
      method: "POST",
      body: JSON.stringify(brief),
    }),

  // ---------------------------------------------------------------------------
  // Planning phase
  // ---------------------------------------------------------------------------

  /**
   * Send a message to the AI planner. PLANNING phase only.
   * Returns updated session with the new user + assistant messages appended.
   */
  sendPlanningMessage: (sessionId: string, message: string): Promise<Session> =>
    request<Session>(`/session/${sessionId}/planning/message`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  /**
   * Ask the AI to produce a full StoryboardPlan from the brief + conversation.
   * Sets plan_status = "draft". Session remains in PLANNING phase.
   */
  generatePlan: (sessionId: string): Promise<Session> =>
    request<Session>(`/session/${sessionId}/planning/plan`, {
      method: "POST",
    }),

  /**
   * Approve the draft plan and transition to STORYBOARD phase.
   * Creates Shot objects from the plan; plan_status becomes "approved".
   */
  approvePlan: (sessionId: string): Promise<Session> =>
    request<Session>(`/session/${sessionId}/planning/approve`, {
      method: "POST",
    }),

  // ---------------------------------------------------------------------------
  // Storyboard phase
  // ---------------------------------------------------------------------------

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
