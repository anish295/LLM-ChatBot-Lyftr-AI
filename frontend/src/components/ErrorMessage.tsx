import type { ErrorItem } from "../types";

interface Props {
  item: ErrorItem;
  onRetry?: (item: ErrorItem) => void;
  disabled?: boolean;
}

const TITLES: Record<ErrorItem["errorKind"], string> = {
  validation: "Message not sent",
  unavailable: "Providers unavailable",
  not_found: "Not found",
  rate_limited: "Slow down",
  server: "Server error",
  network: "Connection problem",
  timeout: "Timed out",
};

/** Errors render inline in the chat (never as assistant-message: they have no metadata). */
export function ErrorMessage({ item, onRetry, disabled }: Props) {
  return (
    <div className="msg msg-error" role="alert" data-testid="error-message">
      <div className="bubble bubble-error">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="err-icon">
          <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
          <path d="M12 7v6M12 16.5v.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <div className="err-text">
          <strong>{TITLES[item.errorKind]}</strong>
          <span>{item.message}</span>
        </div>
        {onRetry && item.errorKind !== "validation" && (
          <button className="btn btn-sm retry-btn" onClick={() => onRetry(item)} disabled={disabled} data-testid="retry-button">
            Retry
          </button>
        )}
      </div>
    </div>
  );
}
