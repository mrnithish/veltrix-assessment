export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---- contract types ----------------------------------------------------------------------------

export type Route = "rag" | "tool" | "hybrid" | "clarify" | "no_answer" | "refuse";

export interface Citation {
  doc_id: string;
  locator: string;
}

export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  status: "pending_confirmation" | "success" | "error";
}

export interface ChatResponse {
  request_id: string;
  answer: string;
  route: Route;
  citations: Citation[];
  tool_calls: ToolCall[];
  pending_confirmation: boolean;
}

// ---- app types ---------------------------------------------------------------------------------

export interface Profile {
  employee_id: string;
  full_name: string;
  email: string;
  role: "employee" | "manager" | "hr";
  region: string;
  level: string;
  join_date: string;
  length_of_service: string;
  manager_id: string | null;
  direct_reports: { employee_id: string; full_name: string; level: string }[];
  today: string;
  now?: string; // server date-time in APP_TIMEZONE
  timezone?: string;
}

export interface CatalogModel {
  id: string;
  listed_by_provider: boolean;
  curated: boolean;
  default: boolean;
  note?: string | null;
}

export interface ModelProbe {
  ok: boolean;
  provider: string;
  model: string;
  latency_ms: number;
  reply?: string;
  status?: number | null;
  error?: string;
}

export interface UsageRow {
  [key: string]: string | number | null;
}

export interface Usage {
  days: number;
  totals: { calls: number; requests: number; prompt_tokens: number; completion_tokens: number; corpus_tokens: number;
    max_corpus_tokens: number; avg_latency_ms: number; errors: number; fallbacks: number };
  by_purpose: { purpose: string; calls: number; prompt_tokens: number; completion_tokens: number;
    avg_corpus_tokens: number; max_corpus_tokens: number; avg_latency_ms: number }[];
  by_model: { provider: string; model: string; calls: number; tokens: number; avg_latency_ms: number; errors: number }[];
  by_day: { day: string; calls: number; prompt_tokens: number; completion_tokens: number; corpus_tokens: number }[];
  corpus_budget: { bucket: string; calls: number }[];
  recent: { ts: string; request_id: string; provider: string; requested_model: string; model: string; purpose: string;
    prompt_tokens: number; completion_tokens: number; corpus_tokens: number; latency_ms: number; outcome: string;
    attempts: { model: string; outcome: string; ms: number }[] }[];
  mine?: Usage["totals"];
}

export interface McpTokenInfo {
  token: string;
  url: string;
  expires_in_days: number;
  tools: string[];
  configs: { claude_code: string; cursor: unknown; vscode: unknown; claude_desktop: unknown };
}

export interface DemoAccount {
  employee_id: string;
  role: string;
  region: string;
  level: string;
  direct_reports: number;
}

export interface LeaveRequest {
  request_id: string;
  leave_type: string;
  start_date: string;
  end_date: string;
  working_days: number;
  status: "pending" | "approved" | "cancelled";
  created_at: string;
  cancellable?: boolean;
  employee_id?: string;
  full_name?: string;
}

export interface MyLeave {
  balances: Record<string, number>;
  requests: LeaveRequest[];
  today: string;
}

export interface TeamView {
  start_date: string;
  end_date: string;
  team: { employee_id: string; full_name: string; level: string; region: string }[];
  leave: LeaveRequest[];
}

export interface Holiday {
  date: string;
  weekday: string;
  name: string;
  kind: "public" | "restricted";
}

export interface Holidays {
  year: number;
  calendar: { doc_id: string; title: string; effective_date: string } | null;
  holidays: Holiday[];
}

export interface DocumentInfo {
  doc_id: string;
  title: string;
  doc_type: string;
  regions: string[];
  effective_date: string;
  access_level: string;
  status: "in_effect" | "upcoming" | "other";
  authoritative: boolean;
  region_specific: boolean;
  sections: string[];
}

export interface SessionSummary {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface StoredMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  request_id: string | null;
  response?: ChatResponse;
}

export interface DevInfo {
  llm_provider: string;
  llm_model: string;
  agent_mode: string;
  ready: boolean;
  phoenix_url: string | null;
  ingestion?: { documents: number; chunks: number; holiday_records: number; seconds: number };
}

export interface ProviderStatus {
  provider: string;
  label: string;
  configured: boolean;
  key_env: string;
  default_model: string;
  suggested_models: string[];
}

export interface LlmSelection {
  provider: string;
  model: string;
  agent_mode: "codemode" | "tools";
  providers: ProviderStatus[];
  fallbacks?: string[];
  hedge_after_s?: number;
  llm_timeout_s?: number;
  request_deadline_s?: number;
  corpus_token_budget?: number;
}

export interface TraceStep {
  name: string;
  start_ms: number;
  duration_ms: number;
  error?: string;
  [key: string]: unknown;
}

export interface LlmCall {
  purpose: string;
  provider: string;
  model: string;
  corpus_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  latency_ms: number;
}

export interface Resolution {
  rule: string;
  status: string;
  winners: [string, string][];
  overruled: [string, string, string][];
  upcoming: [string, string, string] | null;
}

export interface Trace {
  request_id: string;
  total_ms: number;
  agent_mode: string;
  llm?: { provider: string; model: string };
  today: string;
  requester: { employee_id: string; role: string; region: string };
  eligibility: Record<string, number>;
  steps: TraceStep[];
  llm_calls: LlmCall[];
  plan_0?: { action: string; code?: string; refuse_reason?: string };
  plan_1?: { action: string; code?: string; refuse_reason?: string };
  searches?: { query: string; as_of: string; hits: string[]; upcoming: string[] }[];
  resolutions?: Resolution[];
  coverage?: string;
  extract?: unknown;
  all_tool_records?: { name: string; args: Record<string, unknown>; status: string; error_kind: string | null;
    duration_ms: number }[];
  pending_proposal?: { name: string; confirmed: boolean };
  leave_type_guard?: string;
  leave_action_guard?: string;
  ungrounded_candidates?: { ref: string; doc_id: string; value: string; reason?: string }[];
  answer_unsupported_numbers?: string[];
  error?: string;
}

/** One live event from POST /chat/stream. */
export interface AgentEvent {
  type: "start" | "phase" | "plan" | "call" | "call_done" | "sandbox" | "llm" | "evidence" | "resolution" | "note"
    | "final" | "error";
  t_ms: number;
  [key: string]: unknown;
}

// ---- client ------------------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let authToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setAuth(token: string | null, unauthorizedHandler?: () => void) {
  authToken = token;
  if (unauthorizedHandler) onUnauthorized = unauthorizedHandler;
}

async function request<T>(path: string, init: RequestInit = {}, employeeId?: string): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (employeeId) headers["X-Employee-Id"] = employeeId;
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers: { ...headers, ...(init.headers || {}) } });
  } catch {
    throw new ApiError(0, "Cannot reach the API. Is the backend running?");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    if (res.status === 401 && authToken && path !== "/auth/login") onUnauthorized?.();
    throw new ApiError(res.status, String(detail));
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  info: () => request<DevInfo>("/dev/info"),
  login: (identifier: string, password: string) =>
    request<{ token: string; profile: Profile }>("/auth/login", {
      method: "POST", body: JSON.stringify({ identifier, password }),
    }),
  demoAccounts: () => request<DemoAccount[]>("/auth/demo-accounts"),
  me: () => request<Profile>("/me"),
  myLeave: () => request<MyLeave>("/me/leave"),
  team: (start: string, end: string) => request<TeamView>(`/me/team?start=${start}&end=${end}`),
  teamMember: (id: string) =>
    request<{ employee_id: string; balances: Record<string, number>; requests: LeaveRequest[] }>(
      `/me/team/${encodeURIComponent(id)}/leave`),
  holidays: (year: number) => request<Holidays>(`/me/holidays?year=${year}`),
  documents: () => request<{ today: string; documents: DocumentInfo[] }>("/me/documents"),
  sessions: () => request<SessionSummary[]>("/sessions"),
  sessionMessages: (id: string) =>
    request<{ session_id: string; messages: StoredMessage[]; pending_proposal: boolean }>(
      `/sessions/${encodeURIComponent(id)}/messages`),
  deleteSession: (id: string) => request<{ deleted: string }>(`/sessions/${encodeURIComponent(id)}`,
    { method: "DELETE" }),
  chat: (employeeId: string, sessionId: string, message: string) =>
    request<ChatResponse>("/chat", { method: "POST", body: JSON.stringify({ session_id: sessionId, message }) },
      employeeId),
  trace: (employeeId: string, requestId: string) => request<Trace>(`/traces/${requestId}`, {}, employeeId),
  llm: () => request<LlmSelection>("/llm"),
  setLlm: (body: { provider?: string; model?: string; agent_mode?: string; reset?: boolean }) =>
    request<LlmSelection>("/llm", { method: "POST", body: JSON.stringify(body) }),
  models: (provider: string, refresh = false) =>
    request<{ provider: string; models: CatalogModel[]; live_count: number; error: string | null }>(
      `/llm/models?provider=${provider}${refresh ? "&refresh=true" : ""}`),
  testModel: (provider: string, model: string) =>
    request<ModelProbe>("/llm/test", { method: "POST", body: JSON.stringify({ provider, model }) }),
  usage: (days = 14) => request<Usage>(`/usage?days=${days}`),
  mcpToken: () => request<McpTokenInfo>("/me/mcp-token", { method: "POST" }),
};

/** POST /chat/stream and call onEvent for each Server-Sent Event. Resolves with the final response. */
export async function streamChat(
  employeeId: string, sessionId: string, message: string, onEvent: (e: AgentEvent) => void, signal?: AbortSignal,
): Promise<ChatResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Employee-Id": employeeId },
      body: JSON.stringify({ session_id: sessionId, message }),
      signal,
    });
  } catch {
    throw new ApiError(0, "Cannot reach the API. Is the backend running?");
  }
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, String(detail));
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: ChatResponse | null = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of chunk.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const event = JSON.parse(line.slice(6)) as AgentEvent;
        onEvent(event);
        if (event.type === "final") final = event.response as ChatResponse;
      }
    }
  }
  if (!final) throw new ApiError(500, "The response ended unexpectedly");
  return final;
}

export function newSessionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `s-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
