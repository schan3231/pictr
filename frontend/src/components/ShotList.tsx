import type { Session, Shot, ShotStatus } from "../types";

interface ShotListProps {
  session: Session;
  selectedShotIndex: number;
  onSelectShot: (i: number) => void;
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

/** Left-panel overview of all shots with status chips and click-to-select. */
export function ShotList({ session, selectedShotIndex, onSelectShot }: ShotListProps) {
  return (
    <div>
      <p className="section-title">
        Shot List — {session.shots.length} shots
      </p>

      <div className="shot-list">
        {session.shots.map((shot: Shot) => {
          const isCurrent = shot.index === session.current_shot_index;
          const isSelected = shot.index === selectedShotIndex;
          const classes = [
            "shot-row",
            isCurrent ? "current" : "",
            isSelected ? "selected" : "",
          ]
            .filter(Boolean)
            .join(" ");

          return (
            <div
              key={shot.shot_id}
              className={classes}
              onClick={() => onSelectShot(shot.index)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && onSelectShot(shot.index)}
            >
              <span className="shot-row-label">
                Shot {shot.index + 1}
                {isCurrent && (
                  <span
                    style={{ marginLeft: 6, fontSize: 10, color: "var(--accent)" }}
                    title="Next to approve"
                  >
                    ▶
                  </span>
                )}
              </span>
              <div className="shot-row-meta">
                {shot.revision > 0 && <span>rev {shot.revision}</span>}
                <span className={`chip chip-${shot.status}`}>
                  {statusLabel(shot.status)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
