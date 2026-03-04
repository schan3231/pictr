import { useEffect, useRef, useState } from "react";
import type { Session } from "../types";
import { PlanSummary } from "./PlanSummary";

interface PlanningPanelProps {
  session: Session;
  loading: boolean;
  onSendMessage: (message: string) => void;
  onGeneratePlan: () => void;
  onApprovePlan: () => void;
}

/**
 * Right-panel UI for the PLANNING phase.
 *
 * Layout (top to bottom):
 *  1. Chat transcript — scrollable history of user + assistant messages
 *  2. Chat input row — textarea + Send button
 *  3. "Generate Storyboard Plan" button
 *  4. Plan summary panel — shown once a plan draft exists
 *  5. "Approve Plan" button — enabled only when plan_status === "draft"
 */
export function PlanningPanel({
  session,
  loading,
  onSendMessage,
  onGeneratePlan,
  onApprovePlan,
}: PlanningPanelProps) {
  const [input, setInput] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll chat transcript when new messages arrive.
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session.planning_messages]);

  function handleSend() {
    const msg = input.trim();
    if (!msg) return;
    setInput("");
    onSendMessage(msg);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Ctrl+Enter or Cmd+Enter sends the message.
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSend();
    }
  }

  const canGeneratePlan = session.plan_status === "none";
  const canApprovePlan = session.plan !== null && session.plan_status === "draft";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* ── Chat transcript ── */}
      <div>
        <p className="section-title">Planning Chat</p>
        <div className="card" style={{ padding: "12px 14px" }}>
          {session.planning_messages.length === 0 ? (
            <p style={{ color: "var(--muted)", fontSize: 13 }}>
              No messages yet. Start by telling the planner what you have in mind.
            </p>
          ) : (
            <div className="planning-chat">
              {session.planning_messages.map((msg, i) => (
                <div key={i} className={`planning-message ${msg.role}`}>
                  <span className="planning-message-role">
                    {msg.role === "user" ? "You" : "AI Planner"}
                  </span>
                  <div className="planning-message-content">{msg.content}</div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* ── Chat input ── */}
      <div>
        <div className="planning-input-row">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Share ideas, ask questions, or describe the mood you want… (Ctrl+Enter to send)"
            disabled={loading}
          />
          <button
            className="btn-primary"
            onClick={handleSend}
            disabled={loading || !input.trim()}
            style={{ whiteSpace: "nowrap" }}
          >
            {loading ? "Sending…" : "Send"}
          </button>
        </div>
      </div>

      {/* ── Generate plan ── */}
      <div>
        <button
          className="btn-primary"
          style={{ width: "100%" }}
          onClick={onGeneratePlan}
          disabled={loading || !canGeneratePlan}
          title={
            !canGeneratePlan
              ? session.plan_status === "approved"
                ? "Plan already approved"
                : "Plan already generated — review below or approve to continue"
              : undefined
          }
        >
          {loading && !canGeneratePlan
            ? "Generating…"
            : "✦ Generate Storyboard Plan"}
        </button>
        {!canGeneratePlan && session.plan_status === "draft" && (
          <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 6 }}>
            Plan generated — review below, then approve to begin shot generation.
          </p>
        )}
      </div>

      {/* ── Plan summary ── */}
      {session.plan && (
        <div>
          <p className="section-title">Draft Plan</p>
          <div className="card">
            <PlanSummary plan={session.plan} />
          </div>
        </div>
      )}

      {/* ── Approve plan ── */}
      {canApprovePlan && (
        <div>
          <button
            className="btn-primary"
            style={{ width: "100%", background: "var(--success)" }}
            onClick={onApprovePlan}
            disabled={loading}
          >
            {loading ? "Approving…" : "✓ Approve Plan — Begin Shot Generation"}
          </button>
          <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 6 }}>
            Approving locks the plan and creates shot placeholders for each planned scene.
          </p>
        </div>
      )}
    </div>
  );
}
