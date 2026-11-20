export type SimStatus = "" | "429" | "500" | "502" | "503";

export interface SimState {
  enabled: boolean;
  oneShot: boolean;
  wildcard: SimStatus;
  perKey: Record<string, SimStatus>;
}

export const initialSim: SimState = { enabled: false, oneShot: true, wildcard: "", perKey: {} };

const STATUSES: SimStatus[] = ["429", "500", "502", "503"];
const LABEL: Record<string, string> = {
  "": "OK (no failure)",
  "429": "429 Rate limited",
  "500": "500 Server error",
  "502": "502 Bad gateway",
  "503": "503 Unavailable",
};

/** Build the X-Simulate-Failure header value, or "" when nothing is selected. */
export function buildSimHeader(sim: SimState): string {
  if (!sim.enabled) return "";
  const parts: string[] = [];
  if (sim.wildcard) parts.push(`*=${sim.wildcard}`);
  for (const [key, status] of Object.entries(sim.perKey)) if (status) parts.push(`${key}=${status}`);
  return parts.join(",");
}

interface Props {
  sim: SimState;
  onChange: (s: SimState) => void;
  keyIds: string[];
  backendEnabled: boolean | null;
}

export function FailureSimulator({ sim, onChange, keyIds, backendEnabled }: Props) {
  const header = buildSimHeader(sim);
  const disabled = backendEnabled === false;
  const preset = (perKey: Record<string, SimStatus>, wildcard: SimStatus = "") =>
    onChange({ ...sim, enabled: true, wildcard, perKey });

  return (
    <div className={`sim ${disabled ? "sim-disabled" : ""}`} data-testid="failure-simulator">
      {disabled && (
        <p className="sim-off" role="note">
          Simulation is switched off on this backend (<code>ENABLE_FAILURE_SIMULATION=false</code>), so the header
          would be ignored.
        </p>
      )}
      <label className="switch">
        <input
          type="checkbox"
          checked={sim.enabled}
          disabled={disabled}
          onChange={(e) => onChange({ ...sim, enabled: e.target.checked })}
          data-testid="sim-enabled"
        />
        <span className="switch-track" aria-hidden="true" />
        <span>Send <code>X-Simulate-Failure</code></span>
      </label>

      <div className="preset-row">
        <button type="button" className="btn btn-sm" disabled={disabled} onClick={() => preset({ key_1: "429" })} data-testid="sim-preset-k1-429">
          key_1 = 429
        </button>
        <button type="button" className="btn btn-sm" disabled={disabled} onClick={() => preset({ key_1: "500" })}>
          key_1 = 500
        </button>
        <button type="button" className="btn btn-sm" disabled={disabled} onClick={() => preset({}, "429")} data-testid="sim-preset-all-429">
          * = 429
        </button>
      </div>

      <div className="sim-grid">
        <label className="sim-row">
          <span className="sim-key">All keys (*)</span>
          <select
            value={sim.wildcard}
            disabled={disabled || !sim.enabled}
            onChange={(e) => onChange({ ...sim, wildcard: e.target.value as SimStatus })}
          >
            {(["", ...STATUSES] as SimStatus[]).map((s) => (
              <option key={s} value={s}>
                {LABEL[s]}
              </option>
            ))}
          </select>
        </label>
        {keyIds.map((key) => (
          <label className="sim-row" key={key}>
            <span className="sim-key mono">{key}</span>
            <select
              value={sim.perKey[key] ?? ""}
              disabled={disabled || !sim.enabled}
              onChange={(e) => onChange({ ...sim, perKey: { ...sim.perKey, [key]: e.target.value as SimStatus } })}
            >
              {(["", ...STATUSES] as SimStatus[]).map((s) => (
                <option key={s} value={s}>
                  {LABEL[s]}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>

      <label className="check">
        <input
          type="checkbox"
          checked={sim.oneShot}
          disabled={disabled}
          onChange={(e) => onChange({ ...sim, oneShot: e.target.checked })}
        />
        Turn off after the next message
      </label>

      <div className="sim-preview">
        <span className="meta-label">Header:</span>{" "}
        <code data-testid="sim-header">{header ? `X-Simulate-Failure: ${header}` : "(not sent)"}</code>
      </div>
    </div>
  );
}
