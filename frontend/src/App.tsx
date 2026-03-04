import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { SESSION_KEY, SessionControls } from "./components/SessionControls";
import { BriefForm } from "./components/BriefForm";
import { PlanningPanel } from "./components/PlanningPanel";
import { ShotList } from "./components/ShotList";
import { ShotCard } from "./components/ShotCard";
import { StoryboardGrid } from "./components/StoryboardGrid";
import { Toast } from "./components/Toast";
import type { Brief, Session } from "./types";
import "./styles.css";

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [selectedShotIndex, setSelectedShotIndex] = useState<number>(0);

  /**
   * Wraps an API call: sets loading, catches errors → toast, updates session.
   * focusIndex: if provided, sets selectedShotIndex after success.
   */
  async function run(fn: () => Promise<Session>, focusIndex?: number): Promise<void> {
    setLoading(true);
    try {
      const updated = await fn();
      setSession(updated);
      if (focusIndex !== undefined && updated.shots.length > 0) {
        setSelectedShotIndex(Math.min(focusIndex, updated.shots.length - 1));
      }
    } catch (err) {
      setToast(err instanceof Error ? err.message : "An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  }

  // Restore session from localStorage on mount.
  useEffect(() => {
    const id = localStorage.getItem(SESSION_KEY);
    if (!id) return;
    api.getSession(id).then((s) => {
      setSession(s);
      setSelectedShotIndex(Math.min(s.current_shot_index, Math.max(0, s.shots.length - 1)));
    }).catch(() => {
      // Stale ID — silently clear it.
      localStorage.removeItem(SESSION_KEY);
    });
  }, []);

  const handleSelectShot = useCallback((i: number) => setSelectedShotIndex(i), []);

  const handleCreateSession = useCallback(() => {
    run(async () => {
      const s = await api.createSession();
      localStorage.setItem(SESSION_KEY, s.session_id);
      return s;
    }, 0);
  }, []);

  const handleClearSession = useCallback(() => {
    localStorage.removeItem(SESSION_KEY);
    setSession(null);
    setSelectedShotIndex(0);
  }, []);

  const handleSubmitBrief = useCallback(
    (brief: Brief) => {
      if (!session) return;
      run(() => api.submitBrief(session.session_id, brief), 0);
    },
    [session],
  );

  const handleGenerate = useCallback(
    (shotIndex: number) => {
      if (!session) return;
      run(() => api.generateShot(session.session_id, shotIndex), shotIndex);
    },
    [session],
  );

  const handleApprove = useCallback(
    (shotIndex: number) => {
      if (!session) return;
      // After approval, advance focus to the next shot (the new current).
      run(() => api.approveShot(session.session_id, shotIndex), shotIndex + 1);
    },
    [session],
  );

  const handleRevise = useCallback(
    (shotIndex: number, feedback: string) => {
      if (!session) return;
      run(() => api.reviseShot(session.session_id, shotIndex, feedback), shotIndex);
    },
    [session],
  );

  const handleSendPlanningMessage = useCallback(
    (message: string) => {
      if (!session) return;
      run(() => api.sendPlanningMessage(session.session_id, message));
    },
    [session],
  );

  const handleGeneratePlan = useCallback(() => {
    if (!session) return;
    run(() => api.generatePlan(session.session_id));
  }, [session]);

  const handleApprovePlan = useCallback(() => {
    if (!session) return;
    run(() => api.approvePlan(session.session_id), 0);
  }, [session]);

  const showShotCard =
    session?.phase === "STORYBOARD" &&
    session.shots.length > 0 &&
    selectedShotIndex < session.shots.length;

  return (
    <>
      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}

      <header className="app-header">
        <span className="logo">PICTR</span>
        <span className="tagline">AI Storyboard Generator</span>
      </header>

      <div className="app-body">
        {/* ── Left panel: controls + brief + shot list ── */}
        <aside className="left-panel">
          <SessionControls
            session={session}
            loading={loading}
            onCreateSession={handleCreateSession}
            onClearSession={handleClearSession}
          />

          {session?.phase === "INTAKE" && (
            <BriefForm loading={loading} onSubmit={handleSubmitBrief} />
          )}

          {session?.phase === "PLANNING" && session.brief && (
            <BriefSummary brief={session.brief} />
          )}

          {session?.phase === "STORYBOARD" && session.brief && (
            <BriefSummary brief={session.brief} />
          )}

          {session?.phase === "STORYBOARD" && (
            <ShotList
              session={session}
              selectedShotIndex={selectedShotIndex}
              onSelectShot={handleSelectShot}
            />
          )}
        </aside>

        {/* ── Right panel: storyboard grid + selected shot card ── */}
        <main className="right-panel">
          {!session && <EmptyState />}

          {session?.phase === "INTAKE" && (
            <div style={{ color: "var(--muted)", padding: "40px 0", textAlign: "center" }}>
              Fill in the creative brief to start planning your storyboard.
            </div>
          )}

          {session?.phase === "PLANNING" && (
            <PlanningPanel
              session={session}
              loading={loading}
              onSendMessage={handleSendPlanningMessage}
              onGeneratePlan={handleGeneratePlan}
              onApprovePlan={handleApprovePlan}
            />
          )}

          {session?.phase === "STORYBOARD" && (
            <>
              <StoryboardGrid
                session={session}
                selectedShotIndex={selectedShotIndex}
                onSelectShot={handleSelectShot}
              />
              {showShotCard && (
                <ShotCard
                  session={session}
                  shotIndex={selectedShotIndex}
                  loading={loading}
                  onGenerate={handleGenerate}
                  onApprove={handleApprove}
                  onRevise={handleRevise}
                />
              )}
            </>
          )}
        </main>
      </div>
    </>
  );
}

function BriefSummary({ brief }: { brief: Brief }) {
  return (
    <div>
      <p className="section-title">Brief</p>
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <BriefRow label="Brand" value={brief.brand_name} />
        <BriefRow label="Product" value={brief.product} />
        <BriefRow label="Audience" value={brief.target_audience} />
        <BriefRow label="Tone" value={brief.tone} />
        <BriefRow label="Platform" value={brief.platform} />
        <BriefRow label="Duration" value={`${brief.duration_seconds}s`} />
      </div>
    </div>
  );
}

function BriefRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", gap: 8 }}>
      <span className="muted" style={{ minWidth: 64, fontSize: 12 }}>{label}</span>
      <span style={{ fontSize: 12 }}>{value}</span>
    </div>
  );
}

function EmptyState() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        gap: 12,
        color: "var(--muted)",
      }}
    >
      <div style={{ fontSize: 48 }}>🎬</div>
      <p style={{ fontSize: 14 }}>Create a session to get started.</p>
    </div>
  );
}
