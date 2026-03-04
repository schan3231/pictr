import type { Session } from "../types";

const SESSION_KEY = "pictr_session_id";

interface SessionControlsProps {
  session: Session | null;
  loading: boolean;
  onCreateSession: () => void;
  onClearSession: () => void;
}

export function SessionControls({
  session,
  loading,
  onCreateSession,
  onClearSession,
}: SessionControlsProps) {
  function handleCopy() {
    if (session) void navigator.clipboard.writeText(session.session_id);
  }

  return (
    <div>
      <p className="section-title">Session</p>
      {session ? (
        <div className="card">
          <div className="session-id-row" style={{ marginBottom: 10 }}>
            <span className="session-id-text" title={session.session_id}>
              {session.session_id}
            </span>
            <button className="btn-ghost" onClick={handleCopy} title="Copy ID">
              📋
            </button>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <span
              className="chip"
              style={{
                background: session.phase === "INTAKE" ? "#1e3a5f" : "#14532d",
                color: session.phase === "INTAKE" ? "#60a5fa" : "#22c55e",
              }}
            >
              {session.phase}
            </span>
            {session.phase === "STORYBOARD" && (
              <span className="muted" style={{ fontSize: 12 }}>
                {session.current_shot_index >= session.shots.length
                  ? `All ${session.shots.length} shots`
                  : `Shot ${session.current_shot_index + 1} / ${session.shots.length}`}
              </span>
            )}
          </div>
          <hr className="divider" style={{ marginTop: 12 }} />
          <button
            className="btn-ghost"
            onClick={() => {
              localStorage.removeItem(SESSION_KEY);
              onClearSession();
            }}
          >
            ✕ Clear session
          </button>
        </div>
      ) : (
        <button
          className="btn-primary"
          onClick={onCreateSession}
          disabled={loading}
          style={{ width: "100%" }}
        >
          {loading ? "Creating…" : "＋ New Session"}
        </button>
      )}
    </div>
  );
}

export { SESSION_KEY };
