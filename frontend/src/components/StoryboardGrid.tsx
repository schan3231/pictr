import type { Session, Shot } from "../types";

interface StoryboardGridProps {
  session: Session;
  selectedShotIndex: number;
  onSelectShot: (i: number) => void;
}

/** Thumbnail grid overview of all shots. Clicking a tile selects it. */
export function StoryboardGrid({ session, selectedShotIndex, onSelectShot }: StoryboardGridProps) {
  if (session.shots.length === 0) return null;

  const allDone =
    session.shots.length > 0 &&
    session.shots.every((s: Shot) => s.status === "approved");

  return (
    <div>
      <p className="section-title">Storyboard</p>

      {allDone && (
        <div className="complete-banner" style={{ marginBottom: 16 }}>
          🎬 All {session.shots.length} shots approved — click any frame to review / revise
        </div>
      )}

      <div className="storyboard-grid">
        {session.shots.map((shot: Shot) => {
          const isSelected = shot.index === selectedShotIndex;
          return (
            <div
              key={shot.shot_id}
              className={`grid-tile${isSelected ? " selected" : ""}`}
              onClick={() => onSelectShot(shot.index)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && onSelectShot(shot.index)}
              title={`Shot ${shot.index + 1} — ${shot.status}`}
            >
              {shot.image_url ? (
                <img
                  src={shot.image_url}
                  alt={`Shot ${shot.index + 1}`}
                  className="grid-tile-img"
                />
              ) : (
                <div className="grid-tile-placeholder">
                  {shot.status === "generating" ? "Generating…" : "Not generated"}
                </div>
              )}
              <div className="grid-tile-meta">
                <span className="grid-tile-label">Shot {shot.index + 1}</span>
                <span className={`chip chip-${shot.status}`} style={{ fontSize: 9, padding: "1px 5px" }}>
                  {shot.status.replace("_", " ")}
                </span>
                {shot.revision > 0 && (
                  <span style={{ fontSize: 10, color: "var(--muted)" }}>rev {shot.revision}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
