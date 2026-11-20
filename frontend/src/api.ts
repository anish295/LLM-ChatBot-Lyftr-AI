// Thin, typed client for the three backend endpoints.

export type ResolutionSource = "LIVE_INFERENCE" | "LLM_CACHE";

export interface ChatMetadata {
  resolution_source: ResolutionSource;
  model: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  key_id: string | null;
  fallback_attempts: number;
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  metadata: ChatMetadata;
}

export interface HistoryMessage {
  role: "user" | "assistant";
  content: string;
  metadata?: Partial<ChatMetadata>;
}

export interface HistoryResponse {
  session_id: string;
  messages: HistoryMessage[];
}

export interface HealthInfo {
  status: string;
  keys_configured: number;
  cache_enabled: boolean;
  simulationEnabled: boolean | null; // from the X-Failure-Simulation response header
}

const RAW_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").trim();
export const API_BASE_URL = (RAW_BASE || "http://localhost:8000").replace(/\/+$/, "");

export type ApiErrorKind = "validation" | "unavailable" | "not_found" | "rate_limited" | "server" | "network" | "timeout";

export class ApiError extends Error {
  constructor(
    public kind: ApiErrorKind,
    public status: number | null,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function describeValidation(detail: unknown): string {
  if (Array.isArray(detail)) {
    const fields = new Set<string>();
    for (const err of detail) {
      const loc = (err as { loc?: unknown[] })?.loc;
      const field = Array.isArray(loc) ? loc[loc.length - 1] : undefined;
      if (typeof field === "string") fields.add(field);
    }
    if (fields.has("message")) {
      return "Your message couldn't be sent: it must contain 1–4000 characters (whitespace alone doesn't count).";
    }
    if (fields.has("session_id")) return "This chat session id is invalid. Start a new chat and try again.";
    if (fields.has("system_prompt")) return "The system prompt is too long (max 4000 characters).";
  }
  return "The request was invalid. Please check your message and try again.";
}

async function toApiError(res: Response): Promise<ApiError> {
  let detail: unknown;
  let isJson = false;
  try {
    detail = (await res.json())?.detail;
    isJson = true;
  } catch {
    detail = undefined;
  }
  // A gateway error without our JSON body (502/504 from the Netlify proxy or Render while
  // the free instance wakes up) is a reachability problem, not an app error: treat it like a
  // network error so the UI shows "waking" and retries.
  if ([502, 503, 504].includes(res.status) && !isJson) {
    return new ApiError("network", res.status, "The server is waking up or unreachable. Please try again.");
  }
  switch (res.status) {
    case 422:
      return new ApiError("validation", 422, describeValidation(detail), detail);
    case 503:
      return new ApiError(
        "unavailable",
        503,
        "All AI providers are currently unavailable. Please try again shortly.",
        detail,
      );
    case 404:
      return new ApiError("not_found", 404, typeof detail === "string" ? detail : "Not found.", detail);
    case 429:
      return new ApiError("rate_limited", 429, "You're sending messages too quickly. Please wait a moment.", detail);
    default:
      return new ApiError("server", res.status, "Something went wrong on the server. Please try again.", detail);
  }
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 90_000): Promise<{ data: T; res: Response }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { ...init, signal: controller.signal });
  } catch (err) {
    if ((err as Error)?.name === "AbortError") {
      throw new ApiError("timeout", null, "The server took too long to respond. Please try again.");
    }
    throw new ApiError("network", null, "Can't reach the server. Check your connection and try again.");
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) throw await toApiError(res);
  return { data: (await res.json()) as T, res };
}

export async function sendChat(params: {
  sessionId: string;
  message: string;
  systemPrompt?: string;
  simulateFailure?: string;
}): Promise<ChatResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (params.simulateFailure) headers["X-Simulate-Failure"] = params.simulateFailure;
  const body: Record<string, string> = { session_id: params.sessionId, message: params.message };
  if (params.systemPrompt && params.systemPrompt.trim()) body.system_prompt = params.systemPrompt.trim();
  const { data } = await request<ChatResponse>("/chat", { method: "POST", headers, body: JSON.stringify(body) });
  return data;
}

export async function fetchHistory(sessionId: string): Promise<HistoryResponse> {
  const { data } = await request<HistoryResponse>(`/sessions/${encodeURIComponent(sessionId)}/messages`);
  return data;
}

export async function fetchHealth(): Promise<HealthInfo> {
  const { data, res } = await request<Omit<HealthInfo, "simulationEnabled">>("/health", {}, 75_000);
  const header = res.headers.get("X-Failure-Simulation");
  return { ...data, simulationEnabled: header === null ? null : header === "enabled" };
}
