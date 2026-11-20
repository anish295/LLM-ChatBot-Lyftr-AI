interface Props {
  value: string;
  onChange: (v: string) => void;
  locked: boolean;
}

const PRESETS = [
  { label: "Pirate", text: "You are a cheerful pirate. Answer in pirate speak, briefly." },
  { label: "Teacher", text: "You are a patient teacher. Explain simply with one example." },
  { label: "Terse", text: "Answer in at most one sentence." },
];

export function SystemPromptField({ value, onChange, locked }: Props) {
  return (
    <div className="field">
      <label htmlFor="system-prompt" className="field-label">
        System prompt <span className="optional">(optional)</span>
      </label>
      <textarea
        id="system-prompt"
        data-testid="system-prompt-input"
        className="field-input"
        rows={4}
        maxLength={4000}
        placeholder="e.g. You are a helpful assistant that answers like a pirate."
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <div className="preset-row">
        {PRESETS.map((p) => (
          <button key={p.label} type="button" className="btn btn-sm" onClick={() => onChange(p.text)}>
            {p.label}
          </button>
        ))}
        {value && (
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => onChange("")}>
            Clear
          </button>
        )}
      </div>
      <p className="panel-hint">
        {locked
          ? "Sent with each message and stored for this session. Leave empty to keep the session's current prompt."
          : "Applies to this session. Empty uses the server default."}
      </p>
    </div>
  );
}
