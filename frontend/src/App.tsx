import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, fetchHealth, fetchHistory, sendChat, type ChatMetadata, type HealthInfo } from "./api";
import { AssistantMessage } from "./components/AssistantMessage";
import { Composer } from "./components/Composer";
import { ErrorMessage } from "./components/ErrorMessage";
import { ArrowIcon, BoltIcon, ChatIcon, CodeIcon, FeatherIcon, GaugeIcon, GlobeIcon, ShieldIcon, SparkIcon } from "./components/Icons";
import { buildSimHeader, FailureSimulator, initialSim, type SimState } from "./components/FailureSimulator";
import { RestoreSession } from "./components/RestoreSession";
import { PanelSection, SettingsPanel } from "./components/SettingsPanel";
import { SystemPromptField } from "./components/SystemPromptField";
import { ThemeToggle } from "./components/ThemeToggle";
import { exportJson, exportMarkdown } from "./export";
import { useTheme } from "./theme";
import type { ChatItem } from "./types";
import { newSessionId, promptKey, uid } from "./utils";

const SUGGESTIONS = [
  { text: "What is the capital of France?", tag: "Quick fact", Icon: GlobeIcon },
  { text: "Explain response caching in one paragraph.", tag: "Explain", Icon: BoltIcon },
  { text: "Write a haiku about failover.", tag: "Creative", Icon: FeatherIcon },
  { text: "Give me three tips for writing clean Python.", tag: "Code", Icon: CodeIcon },
];

const FEATURES = [
  { label: "Key failover", Icon: ShieldIcon },
  { label: "Response cache", Icon: BoltIcon },
  { label: "Per-request tokens", Icon: GaugeIcon },
];

const SLOW_MS = 5000;

export default function App() {
  // A brand-new session on every page load (never persisted across reloads).
  const [sessionId, setSessionId] = useState(newSessionId);
  const { theme, toggle: toggleTheme } = useTheme();
  const [items, setItems] = useState<ChatItem[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  // Tools panel starts closed; the Tools button opens it.
  const [panelOpen, setPanelOpen] = useState(false);
  const [sim, setSim] = useState<SimState>(initialSim);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [healthState, setHealthState] = useState<"checking" | "waking" | "ok" | "down">("checking");
  const scrollRef = useRef<HTMLDivElement>(null);
  // Fastest LIVE_INFERENCE latency seen per prompt (this page only) for the cache speed-up chip.
  const liveLatency = useRef(new Map<string, number>());

  // Health monitor: probes /health on load (which also wakes a sleeping free-tier backend),
  // retries with backoff while it is unreachable, re-checks every minute and on tab focus.
  // A single failed probe (cold start, redeploy) therefore never leaves the UI stuck "down".
  const probeTimer = useRef<number | undefined>(undefined);
  const probeInFlight = useRef(false);
  const failingSince = useRef<number | null>(null);
  const backoff = useRef(5_000);
  const probe = useCallback(async () => {
    if (probeInFlight.current) return;
    probeInFlight.current = true;
    window.clearTimeout(probeTimer.current);
    let next: number;
    try {
      const h = await fetchHealth();
      setHealth(h);
      setHealthState("ok");
      failingSince.current = null;
      backoff.current = 5_000;
      next = 60_000;
    } catch {
      failingSince.current ??= Date.now();
      // First ~90 s of failures look like a free-tier cold start; after that, call it down.
      setHealthState(Date.now() - failingSince.current < 90_000 ? "waking" : "down");
      next = backoff.current;
      backoff.current = Math.min(backoff.current * 2, 30_000);
    } finally {
      probeInFlight.current = false;
    }
    probeTimer.current = window.setTimeout(probe, next);
  }, []);

  useEffect(() => {
    void probe();
    const onVisible = () => document.visibilityState === "visible" && void probe();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.clearTimeout(probeTimer.current);
    };
  }, [probe]);

  const keyIds = Array.from({ length: Math.max(health?.keys_configured ?? 2, 1) }, (_, i) => `key_${i + 1}`);

  useEffect(() => {
    const el = scrollRef.current;
    // Only follow the conversation; never scroll the empty-state hero out of view.
    if (el && (items.length > 0 || busy)) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [items, busy, slow]);

  const newChat = useCallback(() => {
    setSessionId(newSessionId());
    setItems([]);
    setInput("");
    setAnnouncement("Started a new chat.");
  }, []);

  const restore = useCallback(async (id: string): Promise<string | null> => {
    try {
      const history = await fetchHistory(id);
      const restored: ChatItem[] = [];
      let lastUser = "";
      for (const m of history.messages) {
        if (m.role === "user") {
          lastUser = m.content;
          restored.push({ kind: "user", id: uid(), content: m.content });
        } else {
          const meta = m.metadata ?? {};
          const metadata: ChatMetadata = {
            resolution_source: meta.resolution_source ?? "LIVE_INFERENCE",
            model: meta.model ?? "unknown",
            latency_ms: meta.latency_ms ?? 0,
            input_tokens: meta.input_tokens ?? 0,
            output_tokens: meta.output_tokens ?? 0,
            key_id: meta.key_id ?? null,
            fallback_attempts: meta.fallback_attempts ?? 0,
          };
          restored.push({ kind: "assistant", id: uid(), content: m.content, metadata, prompt: lastUser.trim() });
        }
      }
      setSessionId(history.session_id);
      setItems(restored);
      setAnnouncement(`Restored session ${history.session_id} with ${history.messages.length} messages.`);
      return null;
    } catch (err) {
      if (err instanceof ApiError && err.kind === "not_found") return "Session not found.";
      return err instanceof ApiError ? err.message : "Could not load that session.";
    }
  }, []);

  const send = useCallback(
    async (text: string, retryOf?: string) => {
      if (busy || text.length === 0) return;
      const simulate = buildSimHeader(sim) || undefined;
      if (simulate && sim.oneShot) setSim((s) => ({ ...s, enabled: false }));
      if (retryOf) {
        // Retry: drop the error card and resend; the user bubble is already on screen.
        setItems((prev) => prev.filter((i) => i.id !== retryOf));
      } else {
        setInput(""); // contract: chat-input is empty after sending
        setItems((prev) => [...prev, { kind: "user", id: uid(), content: text, simulate }]);
      }
      setBusy(true);
      setSlow(false);
      const slowTimer = setTimeout(() => setSlow(true), SLOW_MS);
      const attempt = () => sendChat({ sessionId, message: text, systemPrompt, simulateFailure: simulate });
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
        const key = promptKey(text);
        let speedup: number | null = null;
        if (res.metadata.resolution_source === "LIVE_INFERENCE") {
          const prev = liveLatency.current.get(key);
          if (prev === undefined || res.metadata.latency_ms < prev) liveLatency.current.set(key, res.metadata.latency_ms);
        } else {
          const live = liveLatency.current.get(key);
          if (live !== undefined) speedup = live / Math.max(res.metadata.latency_ms, 1);
        }
        setItems((prev) => [
          ...prev,
          {
            kind: "assistant",
            speedup,
            id: uid(),
            content: res.reply,
            metadata: res.metadata,
            prompt: text.trim(),
            simulate,
          },
        ]);
        setAnnouncement(`Assistant replied (${res.metadata.resolution_source}).`);
        // Any successful reply proves the backend is up; refresh the pill if it said otherwise.
        if (failingSince.current !== null || !health) void probe();
      } catch (err) {
        const e =
          err instanceof ApiError ? err : new ApiError("server", null, "Something went wrong. Please try again.");
        if (e.kind === "network" || e.kind === "timeout") void probe();
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
    [busy, sessionId, systemPrompt, sim, health, probe],
  );

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <ChatIcon size={20} />
          </span>
          <div>
            <h1>
              Lyftr <span className="brand-accent">Chat</span>
            </h1>
            <p className="subtitle">Key failover · Response caching · Per-request tokens</p>
          </div>
        </div>
        <div className="topbar-actions">
          <button
            type="button"
            className={`status-pill status-${healthState}`}
            data-testid="backend-status"
            title="Backend /health: click to re-check now"
            onClick={() => void probe()}
          >
            <span className="status-dot" aria-hidden="true" />
            <span className="hide-sm">
              {healthState === "checking" && "Connecting…"}
              {healthState === "waking" && "Waking server…"}
              {healthState === "ok" && `Online · ${health?.keys_configured} keys · cache ${health?.cache_enabled ? "on" : "off"}`}
              {healthState === "down" && "Backend unreachable · retrying"}
            </span>
          </button>
          <span className="session-chip" title="Current session id">
            <span className="meta-label">Session</span> <code data-testid="session-id">{sessionId}</code>
          </span>
          <button className="btn" onClick={newChat} disabled={busy} data-testid="new-chat-button" title="Start a new session">
            <PlusIcon /> <span className="hide-sm">New chat</span>
          </button>
          <button
            className={`btn ${panelOpen ? "btn-active" : ""}`}
            onClick={() => setPanelOpen((o) => !o)}
            aria-expanded={panelOpen}
            aria-controls="settings-panel"
            data-testid="tools-button"
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
              <div className="hero-orb" aria-hidden="true">
                <SparkIcon size={30} />
              </div>
              <h2>
                How can I help <span className="grad-text">today</span>?
              </h2>
              <p>Every reply shows where it came from, which model and key answered, latency and tokens.</p>
              <ul className="feature-chips" aria-label="Highlights">
                {FEATURES.map(({ label, Icon }) => (
                  <li key={label}>
                    <Icon size={14} /> {label}
                  </li>
                ))}
              </ul>
              <div className="suggestions">
                {SUGGESTIONS.map(({ text, tag, Icon }) => (
                  <button key={text} className="suggestion" onClick={() => send(text)} disabled={busy}>
                    <span className="suggestion-icon" aria-hidden="true">
                      <Icon size={18} />
                    </span>
                    <span className="suggestion-body">
                      <span className="suggestion-tag">{tag}</span>
                      <span className="suggestion-text">{text}</span>
                    </span>
                    <span className="suggestion-arrow" aria-hidden="true">
                      <ArrowIcon size={16} />
                    </span>
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
            return (
              <ErrorMessage key={item.id} item={item} disabled={busy} onRetry={(e) => send(e.retryText, e.id)} />
            );
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
        <SystemPromptField value={systemPrompt} onChange={setSystemPrompt} />
        <Composer value={input} onChange={setInput} onSend={() => send(input)} busy={busy} />
      </footer>
      </div>

      <SettingsPanel open={panelOpen} onClose={() => setPanelOpen(false)}>
        <PanelSection
          title="Failure simulator"
          hint={
            <>
              Make chosen keys fail for one request to watch failover live. Simulated requests skip the cache read so
              the surviving key gives a real answer.
            </>
          }
        >
          <FailureSimulator sim={sim} onChange={setSim} keyIds={keyIds} backendEnabled={health?.simulationEnabled ?? null} />
        </PanelSection>
        <PanelSection title="History" hint="Reloads a stored conversation from SQLite via GET /sessions/{id}/messages.">
          <p className="session-line">
            Current session: <code>{sessionId}</code>
          </p>
          <RestoreSession onRestore={restore} disabled={busy} />
        </PanelSection>
        <PanelSection title="Export">
          <div className="preset-row">
            <button className="btn btn-sm" disabled={items.length === 0} onClick={() => exportMarkdown(sessionId, items)} data-testid="export-md">
              Markdown
            </button>
            <button className="btn btn-sm" disabled={items.length === 0} onClick={() => exportJson(sessionId, items)} data-testid="export-json">
              JSON
            </button>
          </div>
        </PanelSection>
      </SettingsPanel>
      </div>

      <div className="sr-only" aria-live="polite" role="status">
        {announcement}
      </div>
    </div>
  );
}

function PlusIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
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
