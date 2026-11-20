import { useState } from "react";

interface Props {
  onRestore: (sessionId: string) => Promise<string | null>; // returns an error message or null
  disabled: boolean;
}

/** Load a past session through GET /sessions/{id}/messages and continue it. */
export function RestoreSession({ onRestore, disabled }: Props) {
  const [value, setValue] = useState("");
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [loading, setLoading] = useState(false);

  return (
    <form
      className="restore"
      onSubmit={async (e) => {
        e.preventDefault();
        const id = value.trim();
        if (!id) return;
        setLoading(true);
        const err = await onRestore(id);
        setLoading(false);
        setStatus(err ? { ok: false, text: err } : { ok: true, text: `Restored ${id}` });
        if (!err) setValue("");
      }}
    >
      <label htmlFor="restore-id" className="field-label">
        Restore session by id
      </label>
      <div className="restore-row">
        <input
          id="restore-id"
          className="field-input mono"
          placeholder="s-1a2b3c4d"
          value={value}
          maxLength={128}
          onChange={(e) => setValue(e.target.value)}
          data-testid="restore-input"
        />
        <button className="btn" type="submit" disabled={disabled || loading || !value.trim()} data-testid="restore-button">
          {loading ? "Loading…" : "Load"}
        </button>
      </div>
      {status && (
        <p className={`restore-status ${status.ok ? "ok" : "bad"}`} role="status">
          {status.text}
        </p>
      )}
    </form>
  );
}
