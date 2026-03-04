/**
 * TypeScript mirrors of the backend Pydantic models.
 * Keep in sync with backend/app/models.py.
 */

export type PhaseType = "INTAKE" | "STORYBOARD";

export type ShotStatus =
  | "draft"
  | "generating"
  | "ready"
  | "approved"
  | "needs_changes"
  | "failed";

export type Platform = "youtube" | "tv";

export interface Brief {
  brand_name: string;
  product: string;
  target_audience: string;
  tone: string;
  platform: Platform;
  duration_seconds: number;
}

export interface Shot {
  shot_id: string;
  index: number;
  status: ShotStatus;
  revision: number;
  image_url: string | null;
  dialogue_text: string | null;
  sfx_notes: string | null;
  camera_notes: string | null;
  user_feedback: string | null;
}

export interface Session {
  session_id: string;
  phase: PhaseType;
  brief: Brief | null;
  shots: Shot[];
  current_shot_index: number;
  created_at: string;
  updated_at: string;
}
