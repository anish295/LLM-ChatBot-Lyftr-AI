import type { AssistantItem } from "../types";

interface Props {
  item: AssistantItem;
}

/**
 * One assistant reply plus the metadata of the request that produced it.
 * Contract: every meta-* element's text content is exactly the value; labels live
 * outside those elements.
 */
export function AssistantMessage({ item }: Props) {
  const m = item.metadata;
  const cached = m.resolution_source === "LLM_CACHE";
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
        </div>
      </div>
    </article>
  );
}
