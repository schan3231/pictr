import type { StoryboardPlan } from "../types";

interface PlanSummaryProps {
  plan: StoryboardPlan;
}

/**
 * Read-only view of a StoryboardPlan.
 * Shows title, logline, narrative beats, and per-shot intent.
 * Does NOT display image_prompt (too verbose for the UI).
 */
export function PlanSummary({ plan }: PlanSummaryProps) {
  return (
    <div className="plan-summary">
      <div>
        <p className="plan-summary-title">{plan.title}</p>
        <p className="plan-logline">{plan.logline}</p>
      </div>

      {plan.beats.length > 0 && (
        <div>
          <p className="section-title" style={{ marginBottom: 6 }}>Narrative Beats</p>
          <div className="plan-beats-list">
            {plan.beats.map((beat) => (
              <div key={beat.index} className="plan-beat">
                <p className="plan-beat-name">{beat.name}</p>
                <p className="plan-beat-desc">{beat.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {plan.shots.length > 0 && (
        <div>
          <p className="section-title" style={{ marginBottom: 6 }}>
            Shot Plan — {plan.shots.length} shots
          </p>
          <div className="plan-shots-list">
            {plan.shots.map((shot) => (
              <div key={shot.index} className="plan-shot-item">
                <p className="plan-shot-index">Shot {shot.index + 1}</p>
                <p className="plan-shot-title">{shot.short_title}</p>
                <p className="plan-shot-purpose">{shot.purpose}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
