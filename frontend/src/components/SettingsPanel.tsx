import type { ReactNode } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

/** Right-hand drawer (overlay on small screens) holding session tools. */
export function SettingsPanel({ open, onClose, children }: Props) {
  return (
    <>
      <div className={`scrim ${open ? "scrim-open" : ""}`} onClick={onClose} aria-hidden="true" />
      <aside id="settings-panel" className={`panel ${open ? "panel-open" : ""}`} aria-label="Session settings">
        <div className="panel-head">
          <h2>Session tools</h2>
          <button className="btn btn-ghost icon-btn" onClick={onClose} aria-label="Close panel">
            <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        <div className="panel-body">{children}</div>
      </aside>
    </>
  );
}

export function PanelSection({ title, hint, children }: { title: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel-section">
      <h3>{title}</h3>
      {hint && <p className="panel-hint">{hint}</p>}
      {children}
    </section>
  );
}
