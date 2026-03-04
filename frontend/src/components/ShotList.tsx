import type { Session, Shot, ShotStatus } from "../types";

interface ShotListProps {
  session: Session;
}

function statusLabel(status: ShotStatus): string {
  const map: Record<ShotStatus, string> = {
    draft: "Draft",
    generating: "Generating…",
    ready: "Ready",
    approved: "Approved",
    needs_changes: "Needs Changes",
    failed: "Failed",
  };
  return map[status];
}

/** Left-panel overview of all shots with status chips. */
export function ShotList({ session }: ShotListProps) {
  const allDone =
    session.shots.length > 0 &&
    session.shots.every((s: Shot) => s.status === "approved");

  return (
    <div>
      <p className="section-title">
        Shot List — {session.shots.length} shots
      </p>

      {allDone && (
        <div className="complete-banner" style={{ marginBottom: 12 }}>
          🎬 Storyboard complete!
        </div>
      )}

      <div className="shot-list">
        {session.shots.map((shot: Shot) => (
          <div
            key={shot.shot_id}
            className={`shot-row${shot.index === session.current_shot_index ? " current" : ""}`}
          >
            <span className="shot-row-label">Shot {shot.index + 1}</span>
            <div className="shot-row-meta">
              {shot.revision > 0 && <span>rev {shot.revision}</span>}
              <span className={`chip chip-${shot.status}`}>
                {statusLabel(shot.status)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
