import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, sendChat } from "./api";
import { AssistantMessage } from "./components/AssistantMessage";
import { Composer } from "./components/Composer";
import { ErrorMessage } from "./components/ErrorMessage";
import { PanelSection, SettingsPanel } from "./components/SettingsPanel";
import { SystemPromptField } from "./components/SystemPromptField";
import { ThemeToggle } from "./components/ThemeToggle";
import { useTheme } from "./theme";
import type { ChatItem } from "./types";
import { newSessionId, uid } from "./utils";

const SUGGESTIONS = [
  "What is the capital of France?",
  "Explain response caching in one paragraph.",
  "Write a haiku about failover.",
  "Give me three tips for writing clean Python.",
];

const SLOW_MS = 5000;
const WIDE = "(min-width: 1100px)";

export default function App() {
  // A brand-new session on every page load (never persisted across reloads).
  const [sessionId] = useState(newSessionId);
  const { theme, toggle: toggleTheme } = useTheme();
  const [items, setItems] = useState<ChatItem[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [panelOpen, setPanelOpen] = useState(() => window.matchMedia?.(WIDE).matches ?? false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [items, busy, slow]);

  const send = useCallback(
    async (text: string) => {
      if (busy || text.length === 0) return;
      setInput(""); // contract: chat-input is empty after sending
      setItems((prev) => [...prev, { kind: "user", id: uid(), content: text }]);
      setBusy(true);
      setSlow(false);
      const slowTimer = setTimeout(() => setSlow(true), SLOW_MS);
      const attempt = () => sendChat({ sessionId, message: text, systemPrompt });
      try {
        let res;
        try {
          res = await attempt();
        } catch (err) {
          // Free-tier hosts sleep when idle: a cold start often looks like a network error.
          if (err instanceof ApiError && err.kind === "network") {
            setSlow(true);
            await new Promise((r) => setTimeout(r, 3000));
            res = await attempt();
          } else {
            throw err;
          }
        }
        setItems((prev) => [
          ...prev,
          { kind: "assistant", id: uid(), content: res.reply, metadata: res.metadata, prompt: text.trim() },
        ]);
        setAnnouncement(`Assistant replied (${res.metadata.resolution_source}).`);
      } catch (err) {
        const e =
          err instanceof ApiError ? err : new ApiError("server", null, "Something went wrong. Please try again.");
        setItems((prev) => [
          ...prev,
          { kind: "error", id: uid(), errorKind: e.kind, message: e.message, retryText: text },
        ]);
        setAnnouncement(`Error: ${e.message}`);
      } finally {
        clearTimeout(slowTimer);
        setBusy(false);
        setSlow(false);
      }
    },
    [busy, sessionId, systemPrompt],
  );

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <img src="/favicon.svg" alt="" width={32} height={32} />
          <div>
            <h1>
              Lyftr <span className="brand-accent">Chat</span>
            </h1>
            <p className="subtitle">Key failover · Response caching · Per-request tokens</p>
          </div>
        </div>
        <div className="topbar-actions">
          <span className="session-chip" title="Current session id">
            <span className="meta-label">Session</span> <code data-testid="session-id">{sessionId}</code>
          </span>
          <button
            className={`btn ${panelOpen ? "btn-active" : ""}`}
            onClick={() => setPanelOpen((o) => !o)}
            aria-expanded={panelOpen}
            aria-controls="settings-panel"
          >
            <SlidersIcon /> <span className="hide-sm">Tools</span>
          </button>
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
        </div>
      </header>

      <div className={`workspace ${panelOpen ? "workspace-panel" : ""}`}>
      <div className="conversation">
      <main className="chat" ref={scrollRef}>
        <div className="chat-inner">
          {items.length === 0 && (
            <section className="empty">
              <h2>How can I help today?</h2>
              <p>Every reply shows where it came from, which model and key answered, latency and tokens.</p>
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} className="suggestion" onClick={() => send(s)} disabled={busy}>
                    {s}
                  </button>
                ))}
              </div>
            </section>
          )}

          {items.map((item) => {
            if (item.kind === "user") {
              return (
                <article key={item.id} className="msg msg-user" aria-label="Your message">
                  <div className="bubble bubble-user">{item.content}</div>
                </article>
              );
            }
            if (item.kind === "assistant") return <AssistantMessage key={item.id} item={item} />;
            return <ErrorMessage key={item.id} item={item} />;
          })}

          {busy && (
            <div className="typing" aria-label="Assistant is typing">
              <span />
              <span />
              <span />
              {slow && <em className="warmup">Warming up the server… free-tier hosts can take up to a minute.</em>}
            </div>
          )}
        </div>
      </main>

      <footer className="composer-wrap">
        {systemPrompt.trim() && (
          <div className="active-prompt" title={systemPrompt}>
            <span className="meta-label">System prompt:</span> <span className="active-prompt-text">{systemPrompt}</span>
          </div>
        )}
        <Composer value={input} onChange={setInput} onSend={() => send(input)} busy={busy} />
      </footer>
      </div>

      <SettingsPanel open={panelOpen} onClose={() => setPanelOpen(false)}>
        <PanelSection title="Persona">
          <SystemPromptField value={systemPrompt} onChange={setSystemPrompt} locked={items.some((i) => i.kind === "assistant")} />
        </PanelSection>
      </SettingsPanel>
      </div>

      <div className="sr-only" aria-live="polite" role="status">
        {announcement}
      </div>
    </div>
  );
}

function SlidersIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <circle cx="16" cy="6" r="2" stroke="currentColor" strokeWidth="2" />
      <circle cx="10" cy="12" r="2" stroke="currentColor" strokeWidth="2" />
      <circle cx="18" cy="18" r="2" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}
