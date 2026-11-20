import type { AssistantItem } from "../types";

interface Props {
  item: AssistantItem;
}

function failoverText(keyId: string, attempts: number): string {
  const idx = Number(keyId.replace("key_", ""));
  if (Number.isFinite(idx) && idx - 1 === attempts) {
    const path = Array.from({ length: idx }, (_, i) => `key_${i + 1}`).join(" → ");
    return `Failover: ${path} (${attempts} attempt${attempts === 1 ? "" : "s"})`;
  }
  return `Failover → ${keyId} after ${attempts} failed attempt${attempts === 1 ? "" : "s"}`;
}

/**
 * One assistant reply plus the metadata of the request that produced it.
 * Contract: every meta-* element's text content is exactly the value; labels live
 * outside those elements.
 */
export function AssistantMessage({ item }: Props) {
  const m = item.metadata;
  const cached = m.resolution_source === "LLM_CACHE";
  const failedOver = m.fallback_attempts > 0 && m.key_id;
  return (
    <article className="msg msg-assistant" data-testid="assistant-message" aria-label="Assistant reply">
      <div className="avatar avatar-bot" aria-hidden="true">AI</div>
      <div className="msg-body">
        <div className="bubble bubble-assistant">
          <div className="reply-text">{item.content}</div>
        </div>
        <div className="meta-row" aria-label="Request metadata">
          <span className={`badge ${cached ? "badge-cache" : "badge-live"}`} title="Resolution source">
            <span className="badge-dot" aria-hidden="true" />
            <span data-testid="meta-source">{m.resolution_source}</span>
          </span>
          <span className="meta-item">
            <span className="meta-label">Model</span>
            <span className="meta-value mono" data-testid="meta-model">{m.model}</span>
          </span>
          <span className="meta-item">
            <span className="meta-label">Latency</span>
            <span className="meta-value" data-testid="meta-latency">{m.latency_ms} ms</span>
          </span>
          <span className="meta-item">
            <span className="meta-label">Input tokens:</span>
            <span className="meta-value" data-testid="meta-input-tokens">{m.input_tokens}</span>
          </span>
          <span className="meta-item">
            <span className="meta-label">Output tokens:</span>
            <span className="meta-value" data-testid="meta-output-tokens">{m.output_tokens}</span>
          </span>
          <span className="meta-item" title={cached ? "Cache hits are not served by any key" : "Key that answered"}>
            <span className="meta-label">Key</span>
            <span className="meta-value mono" data-testid="meta-key">{m.key_id ?? "none"}</span>
          </span>
          <span className="meta-item" title="Keys that failed before one succeeded">
            <span className="meta-label">Fallbacks</span>
            <span className="meta-value" data-testid="meta-fallbacks">{m.fallback_attempts}</span>
          </span>
        </div>
        {(failedOver || item.simulate) && (
          <div className="chip-row">
            {failedOver && (
              <span className="chip chip-failover" data-testid="failover-chip">
                <ShieldIcon /> {failoverText(m.key_id!, m.fallback_attempts)}
              </span>
            )}
            {item.simulate && (
              <span className="chip chip-sim" title="This request carried the X-Simulate-Failure header">
                Simulated: <code>{item.simulate}</code>
              </span>
            )}
          </div>
        )}
      </div>
    </article>
  );
}

function ShieldIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6l8-3z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}
