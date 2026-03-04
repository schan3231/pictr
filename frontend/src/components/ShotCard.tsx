import { useState } from "react";
import type { Session } from "../types";

interface ShotCardProps {
  session: Session;
  shotIndex: number;
  loading: boolean;
  onGenerate: (shotIndex: number) => void;
  onApprove: (shotIndex: number) => void;
  onRevise: (shotIndex: number, feedback: string) => void;
}

/**
 * Shot Card panel for a specific shot (identified by shotIndex prop).
 *
 * Covers four states the shot can be in:
 *  1. draft          → offer Generate button
 *  2. ready          → show image + text + Approve / Revise controls
 *  3. needs_changes  → re-show Generate (will pass stored feedback)
 *  4. failed         → show error + offer Regenerate / Revise
 *  5. approved       → show content + Revise (retroactive editing)
 *
 * Approve is only enabled when shotIndex === current_shot_index (sequential gating).
 * Revise is available for ready, approved, needs_changes, and failed shots.
 */
export function ShotCard({
  session,
  shotIndex,
  loading,
  onGenerate,
  onApprove,
  onRevise,
}: ShotCardProps) {
  const [feedback, setFeedback] = useState("");
  const [reviseOpen, setReviseOpen] = useState(false);

  const idx = shotIndex;

  // Guard: out-of-bounds index.
  if (idx < 0 || idx >= session.shots.length) return null;

  const shot = session.shots[idx];
  const isCurrentShot = idx === session.current_shot_index;
  const isComplete = session.current_shot_index >= session.shots.length;
  const canApprove = isCurrentShot || isComplete;
  const canRevise = ["ready", "approved", "needs_changes", "failed"].includes(shot.status);
  const planApproved = session.phase === "STORYBOARD" && session.plan_status === "approved";

  function handleReviseSubmit() {
    if (!feedback.trim()) return;
    onRevise(idx, feedback.trim());
    setFeedback("");
    setReviseOpen(false);
  }

  const textFields = (shot.dialogue_text || shot.sfx_notes || shot.camera_notes) ? (
    <>
      {shot.dialogue_text && (
        <div className="shot-field">
          <p className="shot-field-label">🎤 Dialogue / Voiceover</p>
          <p className="shot-field-value">{shot.dialogue_text}</p>
        </div>
      )}
      {shot.sfx_notes && (
        <div className="shot-field">
          <p className="shot-field-label">🔊 SFX Notes</p>
          <p className="shot-field-value">{shot.sfx_notes}</p>
        </div>
      )}
      {shot.camera_notes && (
        <div className="shot-field">
          <p className="shot-field-label">🎬 Camera</p>
          <p className="shot-field-value">{shot.camera_notes}</p>
        </div>
      )}
    </>
  ) : null;

  const reviseForm = reviseOpen ? (
    <div>
      <div className="form-group">
        <label htmlFor={`feedback-${idx}`}>Revision feedback</label>
        <textarea
          id={`feedback-${idx}`}
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="Describe what to change…"
          rows={3}
        />
      </div>
      <div className="btn-row">
        <button
          className="btn-primary"
          onClick={handleReviseSubmit}
          disabled={loading || !feedback.trim()}
        >
          {loading ? "Submitting…" : "Submit Feedback →"}
        </button>
        <button
          className="btn-ghost"
          onClick={() => {
            setReviseOpen(false);
            setFeedback("");
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  ) : null;

  return (
    <div>
      <p className="section-title">
        Shot {idx + 1} / {session.shots.length}
        {shot.revision > 0 && (
          <span className="muted" style={{ marginLeft: 8, fontWeight: 400 }}>
            (revision {shot.revision})
          </span>
        )}
      </p>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {/* ── Image area ── */}
        {shot.image_url ? (
          <img
            src={shot.image_url}
            alt={`Shot ${idx + 1}`}
            className="shot-card-image"
          />
        ) : (
          <div className="shot-card-image-placeholder">
            {shot.status === "failed"
              ? "Image generation failed"
              : "Image will appear after generation"}
          </div>
        )}

        {/* ── Status badge ── */}
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className={`chip chip-${shot.status}`}>
            {shot.status.replace("_", " ")}
          </span>
          {shot.status === "failed" && shot.dialogue_text && (
            <span style={{ color: "var(--danger)", fontSize: 12 }}>
              {shot.dialogue_text}
            </span>
          )}
        </div>

        {/* ── Generated text fields (ready + approved) ── */}
        {(shot.status === "ready" || shot.status === "approved") && textFields}

        {/* ── Previous feedback ── */}
        {shot.user_feedback && shot.status !== "needs_changes" && (
          <div className="shot-field">
            <p className="shot-field-label">💬 Last Feedback</p>
            <p className="shot-field-value muted">{shot.user_feedback}</p>
          </div>
        )}

        <hr className="divider" />

        {/* ── Plan not approved: gating notice ── */}
        {!planApproved && (
          <p style={{ fontSize: 12, color: "var(--muted)" }}>
            Approve the storyboard plan to begin generating shots.
          </p>
        )}

        {planApproved && (
          <>
            {/* ── draft: Generate ── */}
            {shot.status === "draft" && (
              <div className="btn-row">
                <button
                  className="btn-primary"
                  onClick={() => onGenerate(idx)}
                  disabled={loading}
                >
                  {loading ? "Generating…" : `⚡ Generate Shot ${idx + 1}`}
                </button>
              </div>
            )}

            {/* ── needs_changes: Regenerate ── */}
            {shot.status === "needs_changes" && (
              <div className="btn-row">
                <button
                  className="btn-primary"
                  onClick={() => onGenerate(idx)}
                  disabled={loading}
                >
                  {loading ? "Generating…" : `⚡ Regenerate Shot ${idx + 1}`}
                </button>
              </div>
            )}

            {/* ── ready: Approve + Revise ── */}
            {shot.status === "ready" && (
              <>
                <div className="btn-row">
                  <button
                    className="btn-primary"
                    onClick={() => onApprove(idx)}
                    disabled={loading || !canApprove}
                    title={!canApprove ? "Shots must be approved in order" : undefined}
                  >
                    {loading ? "Saving…" : "✓ Approve"}
                  </button>
                  <button
                    className="btn-secondary"
                    onClick={() => setReviseOpen((v) => !v)}
                    disabled={loading}
                  >
                    ✎ Revise
                  </button>
                </div>
                {!isComplete && !isCurrentShot && (
                  <p style={{ fontSize: 11, color: "var(--muted)" }}>
                    Shot {session.current_shot_index + 1} must be approved first.
                  </p>
                )}
                {isComplete && (
                  <p style={{ fontSize: 11, color: "var(--muted)" }}>
                    Storyboard complete. You can still revise any frame.
                  </p>
                )}
                {reviseForm}
              </>
            )}

            {/* ── approved: Revise only ── */}
            {shot.status === "approved" && canRevise && (
              <>
                <div className="btn-row">
                  <button
                    className="btn-secondary"
                    onClick={() => setReviseOpen((v) => !v)}
                    disabled={loading}
                  >
                    ✎ Revise
                  </button>
                </div>
                {isComplete && (
                  <p style={{ fontSize: 11, color: "var(--muted)" }}>
                    Storyboard complete. You can still revise any frame.
                  </p>
                )}
                {reviseForm}
              </>
            )}

            {/* ── failed: Retry + Revise ── */}
            {shot.status === "failed" && (
              <>
                <div className="btn-row">
                  <button
                    className="btn-danger"
                    onClick={() => onGenerate(idx)}
                    disabled={loading}
                  >
                    {loading ? "Retrying…" : "↺ Retry Generation"}
                  </button>
                  <button
                    className="btn-secondary"
                    onClick={() => setReviseOpen((v) => !v)}
                    disabled={loading}
                  >
                    ✎ Revise
                  </button>
                </div>
                {reviseForm}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
