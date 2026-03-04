/**
 * TypeScript mirrors of the backend Pydantic models.
 * Keep in sync with backend/app/models.py.
 */

export type PhaseType = "INTAKE" | "PLANNING" | "STORYBOARD";

export type ShotStatus =
  | "draft"
  | "generating"
  | "ready"
  | "approved"
  | "needs_changes"
  | "failed";

export type Platform = "youtube" | "tv";

export type PlanStatus = "none" | "draft" | "approved";

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
  image_prompt: string | null;
  image_url: string | null;
  dialogue_text: string | null;
  sfx_notes: string | null;
  camera_notes: string | null;
  user_feedback: string | null;
}

// ---------------------------------------------------------------------------
// Planning phase types
// ---------------------------------------------------------------------------

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface Beat {
  index: number;
  name: string;
  description: string;
}

export interface PlannedShot {
  index: number;
  short_title: string;
  purpose: string;
  visual_description: string;
  key_action: string;
  dialogue_hint: string | null;
  sfx_hint: string | null;
  camera_hint: string | null;
  image_prompt: string;
}

export interface StoryboardPlan {
  title: string;
  logline: string;
  target_audience: string | null;
  tone: string | null;
  beats: Beat[];
  shots: PlannedShot[];
}

// ---------------------------------------------------------------------------
// Session
// ---------------------------------------------------------------------------

export interface Session {
  session_id: string;
  phase: PhaseType;
  brief: Brief | null;
  planning_messages: ChatMessage[];
  plan: StoryboardPlan | null;
  plan_status: PlanStatus;
  shots: Shot[];
  current_shot_index: number;
  created_at: string;
  updated_at: string;
}
