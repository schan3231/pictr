import { useState } from "react";
import type { Session, Shot } from "../types";

interface ShotCardProps {
  session: Session;
  loading: boolean;
  onGenerate: (shotIndex: number) => void;
  onApprove: (shotIndex: number) => void;
  onRevise: (shotIndex: number, feedback: string) => void;
}

/**
 * The active Shot Card panel.
 *
 * Covers four states the current shot can be in:
 *  1. draft          → offer Generate button
 *  2. ready          → show image + text + Approve / Revise controls
 *  3. needs_changes  → re-show Generate (will pass stored feedback)
 *  4. failed         → show error + offer Regenerate
 *
 * All shots are complete: show the completion banner.
 */
export function ShotCard({
  session,
  loading,
  onGenerate,
  onApprove,
  onRevise,
}: ShotCardProps) {
  const [feedback, setFeedback] = useState("");
  const [reviseOpen, setReviseOpen] = useState(false);

  const idx = session.current_shot_index;
  const allDone =
    session.shots.length > 0 &&
    session.shots.every((s: Shot) => s.status === "approved");

  // All shots approved — storyboard is complete.
  if (allDone) {
    return (
      <div>
        <p className="section-title">Storyboard</p>
        <div className="complete-banner">
          🎬 All {session.shots.length} shots approved — storyboard complete!
        </div>
      </div>
    );
  }

  // Guard: shouldn't happen, but keeps TS happy.
  if (idx >= session.shots.length) return null;

  const shot = session.shots[idx];

  function handleReviseSubmit() {
    if (!feedback.trim()) return;
    onRevise(idx, feedback.trim());
    setFeedback("");
    setReviseOpen(false);
  }

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

        {/* ── Generated text fields ── */}
        {shot.status === "ready" && (
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
        )}

        {/* ── Previous feedback ── */}
        {shot.user_feedback && shot.status !== "needs_changes" && (
          <div className="shot-field">
            <p className="shot-field-label">💬 Last Feedback</p>
            <p className="shot-field-value muted">{shot.user_feedback}</p>
          </div>
        )}

        <hr className="divider" />

        {/* ── Action buttons ── */}
        {(shot.status === "draft" || shot.status === "needs_changes") && (
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

        {shot.status === "ready" && (
          <>
            <div className="btn-row">
              <button
                className="btn-primary"
                onClick={() => onApprove(idx)}
                disabled={loading}
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

            {reviseOpen && (
              <div>
                <div className="form-group">
                  <label htmlFor="feedback">Revision feedback</label>
                  <textarea
                    id="feedback"
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
            )}
          </>
        )}

        {shot.status === "failed" && (
          <div className="btn-row">
            <button
              className="btn-danger"
              onClick={() => onGenerate(idx)}
              disabled={loading}
            >
              {loading ? "Retrying…" : "↺ Retry Generation"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
