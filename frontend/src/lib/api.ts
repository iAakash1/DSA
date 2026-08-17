/**
 * API client.
 *
 * Every request goes to the FastAPI backend. The browser never holds a Groq,
 * YouTube or Supabase service key — only the user's session token, which the
 * backend verifies on every call.
 */

import { getAccessToken } from './auth';

const BASE = '/api';

export class ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await getAccessToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init.headers as Record<string, string>) ?? {}),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the CP-Forge server. Is the backend running?');
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const body = text ? safeParse(text) : null;

  if (!response.ok) {
    const error = (body as { error?: { code: string; message: string; details?: Record<string, unknown> } })?.error;
    throw new ApiError(
      response.status,
      error?.code ?? 'error',
      error?.message ?? `Request failed (${response.status})`,
      error?.details,
    );
  }

  return body as T;
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function qs(params: Record<string, unknown> = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : '';
}

export const api = {
  health: () => request<Health>('/health'),
  me: () => request<Me>('/me'),
  updateMe: (body: Record<string, unknown>) => request<unknown>('/me', { method: 'PATCH', body: JSON.stringify(body) }),
  updateSettings: (body: Record<string, unknown>) =>
    request<unknown>('/me/settings', { method: 'PATCH', body: JSON.stringify(body) }),
  connectAccount: (body: { platform: string; username: string }) =>
    request<unknown>('/me/accounts', { method: 'POST', body: JSON.stringify(body) }),
  reference: () => request<Reference>('/reference'),

  dashboard: () => request<Dashboard>('/dashboard'),

  problems: (params: Record<string, unknown>) => request<Paged<Problem>>(`/problems${qs(params)}`),
  problem: (id: string) => request<ProblemDetail>(`/problems/${id}`),
  addProblem: (body: Record<string, unknown>) =>
    request<Problem & { created: boolean }>('/problems', { method: 'POST', body: JSON.stringify(body) }),
  solve: (id: string, body: Record<string, unknown>) =>
    request<SolveResult>(`/problems/${id}/solve`, { method: 'POST', body: JSON.stringify(body) }),
  attempt: (id: string, body: Record<string, unknown>) =>
    request<unknown>(`/problems/${id}/attempt`, { method: 'POST', body: JSON.stringify(body) }),
  setStatus: (id: string, status: string) =>
    request<unknown>(`/problems/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  addNote: (id: string, body: Record<string, unknown>) =>
    request<unknown>(`/problems/${id}/notes`, { method: 'POST', body: JSON.stringify(body) }),
  resources: (id: string, refresh = false) =>
    request<Resources>(`/problems/${id}/resources${qs({ refresh })}`),
  search: (q: string) => request<SearchResults>(`/problems/search${qs({ q })}`),

  sheets: () => request<Sheet[]>('/sheets'),
  sheet: (slug: string) => request<SheetDetail>(`/sheets/${slug}`),
  sheetProblems: (slug: string, params: Record<string, unknown> = {}) =>
    request<{ items: SheetProblem[]; total: number }>(`/sheets/${slug}/problems${qs(params)}`),

  collections: () => request<Collection[]>('/collections'),
  createCollection: (body: { name: string; description?: string; color?: string }) =>
    request<Collection>('/collections', { method: 'POST', body: JSON.stringify(body) }),
  addToCollection: (slug: string, problemId: string) =>
    request<unknown>(`/collections/${slug}/problems`, {
      method: 'POST',
      body: JSON.stringify({ problem_id: problemId }),
    }),

  stats: () => request<Stats>('/stats'),
  topics: () => request<{ items: Mastery[]; untouched: { slug: string; name: string }[] }>('/stats/topics'),
  patterns: () => request<{ items: Mastery[] }>('/stats/patterns'),
  weaknesses: () => request<WeaknessSummary>('/stats/weaknesses'),
  difficulty: () => request<DifficultyProgression>('/stats/difficulty'),
  mistakes: () => request<MistakeDistribution>('/stats/mistakes'),
  solveTime: () => request<{ summary: Record<string, number | null>; by_topic: TopicTime[] }>('/stats/time'),

  recommendations: () => request<Recommendation[]>('/recommendations'),
  refreshRecommendations: () => request<Recommendation[]>('/recommendations/refresh', { method: 'POST' }),
  missions: () => request<Mission[]>('/missions'),
  reviews: (includeUpcoming = false) =>
    request<{ due_count: number; items: Review[] }>(`/reviews${qs({ include_upcoming: includeUpcoming })}`),
  completeReview: (id: string, outcome: string) =>
    request<unknown>(`/reviews/${id}/complete`, { method: 'POST', body: JSON.stringify({ outcome }) }),

  heatmap: () => request<Heatmap>('/activity/heatmap'),
  activityDay: (day: string) => request<DayDetail>(`/activity/day/${day}`),
  recentActivity: () => request<RecentActivity[]>('/activity/recent'),

  achievements: () => request<AchievementList>('/achievements'),
  gamification: () => request<Gamification>('/gamification'),
  freezes: () => request<FreezeState>('/freezes'),
  buyFreeze: () => request<{ purchased: boolean; reason?: string; balance: number }>('/freezes/purchase', { method: 'POST' }),

  contests: () => request<{ summary: ContestSummary; items: Contest[] }>('/contests'),
  syncContests: () => request<unknown>('/contests/sync/codeforces', { method: 'POST' }),

  sync: (platform: string) => request<SyncResult>(`/sync/${platform}`, { method: 'POST' }),
  syncAll: () => request<{ results: SyncResult[] }>('/sync', { method: 'POST' }),
  syncStatus: () => request<AccountStatus[]>('/sync/status'),

  icpc: () => request<IcpcDashboard>('/icpc'),
  icpcSettings: (body: Record<string, unknown>) =>
    request<IcpcSettings>('/icpc/settings', { method: 'PUT', body: JSON.stringify(body) }),
  icpcRoadmap: () => request<IcpcRoadmap>('/icpc/roadmap'),
  icpcTopic: (key: string, body: Record<string, unknown>) =>
    request<unknown>(`/icpc/roadmap/${key}`, { method: 'PUT', body: JSON.stringify(body) }),
  icpcTemplates: () => request<TemplateSummary[]>('/icpc/templates'),
  icpcTemplate: (slug: string) => request<TemplateDetail>(`/icpc/templates/${slug}`),
  icpcReviewTemplate: (slug: string, body: Record<string, unknown>) =>
    request<unknown>(`/icpc/templates/${slug}/review`, { method: 'POST', body: JSON.stringify(body) }),
  icpcContests: () => request<VirtualContest[]>('/icpc/contests'),
  icpcCreateContest: (body: { name: string; problem_ids: string[]; duration_minutes?: number }) =>
    request<VirtualContest>('/icpc/contests', { method: 'POST', body: JSON.stringify(body) }),
  icpcUpdateContestProblem: (contestId: string, problemId: string, body: Record<string, unknown>) =>
    request<unknown>(`/icpc/contests/${contestId}/problems/${problemId}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  icpcFinishContest: (contestId: string) =>
    request<VirtualContest>(`/icpc/contests/${contestId}/finish`, { method: 'POST' }),
  icpcUpsolve: () => request<UpsolveItem[]>('/icpc/upsolve'),
  icpcReadiness: () => request<Readiness>('/icpc/readiness'),
  icpcSnapshot: () => request<Readiness>('/icpc/readiness/snapshot', { method: 'POST' }),

  aiStatus: () => request<AiStatus>('/ai/status'),
  aiDaily: (force = false) => request<Insight>(`/ai/daily${qs({ force })}`),
  aiWeekly: (force = false) => request<Insight>(`/ai/weekly${qs({ force })}`),
  aiWeaknesses: (force = false) => request<Insight>(`/ai/weaknesses${qs({ force })}`),
  aiStudyPlan: (force = false) => request<Insight>(`/ai/study-plan${qs({ force })}`),
  aiChat: (message: string, conversationId?: string) =>
    request<ChatResponse>('/ai/chat', {
      method: 'POST',
      body: JSON.stringify({ message, conversation_id: conversationId }),
    }),
  aiUsage: () => request<AiUsage>('/ai/usage'),

  exportData: () => request<Record<string, unknown>>('/export'),
};

/* ---- types ---- */

export interface Health {
  status: string;
  features: {
    auth_mode: string;
    supabase_configured: boolean;
    ai_configured: boolean;
    ai_model: string | null;
    youtube_configured: boolean;
  };
}

export interface Me {
  id: string;
  username: string;
  display_name: string | null;
  timezone: string;
  settings: Record<string, number | boolean | string | null>;
  accounts: AccountStatus[];
  ai_available: boolean;
}

export interface AccountStatus {
  platform: string;
  username: string;
  connected: boolean;
  last_synced_at: string | null;
  last_sync_status: string | null;
  last_sync_error: string | null;
  current_rating: number | null;
  max_rating: number | null;
}

export interface Reference {
  mistake_types: { value: string; label: string }[];
  solution_sources: { value: string; label: string }[];
  statuses: { value: string; label: string }[];
  levels: { level: number; xp_required: number; rank: string }[];
}

export interface Paged<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export interface Problem {
  id: string;
  platform: string;
  external_id: string;
  title: string;
  url: string;
  rating: number | null;
  difficulty: string;
  tags: string[];
  status: string;
  attempts: number;
  solved_at: string | null;
  solution_source: string | null;
  needs_review: boolean;
  is_favorite: boolean;
  time_spent_seconds: number;
}

export interface ProblemDetail extends Problem {
  topics: { slug: string; name: string; path: string }[];
  patterns: { slug: string; name: string }[];
  sheets: { slug: string; name: string; section: string | null; rating_bucket: number | null }[];
  collections: { slug: string; name: string }[];
  sessions: Session[];
  notes: Note[];
  mistakes: { id: string; type: string; occurred_at: string }[];
  resources: ResourceItem[];
  review: { id: string; reason: string; reason_detail: string; scheduled_for: string } | null;
  related: RelatedProblem[];
}

export interface RelatedProblem {
  id: string;
  title: string;
  platform: string;
  external_id: string;
  url: string;
  rating: number | null;
  difficulty: string;
  shared_topics: number;
}

export interface Session {
  id: string;
  finished_at: string | null;
  time_spent_seconds: number | null;
  attempt_count: number;
  result: string;
  solution_source: string;
  confidence: number | null;
  approach: string | null;
  notes: string | null;
}

export interface Note {
  id: string;
  kind: string;
  content_md: string;
  created_at: string;
}

export interface ResourceItem {
  id: string;
  kind: string;
  title: string;
  url: string;
  external_id: string | null;
  channel_title: string | null;
  duration_seconds: number | null;
  score: number;
  is_selected: boolean;
}

export interface Resources {
  available: boolean;
  message?: string;
  selected: ResourceItem | null;
  candidates: ResourceItem[];
}

export interface SearchResults {
  problems: Problem[];
  topics: { slug: string; name: string }[];
  patterns: { slug: string; name: string }[];
  sheets: { slug: string; name: string }[];
}

export interface DatasetStatus {
  state: 'complete' | 'partial';
  loaded: number;
  expected: number | null;
  label: string | null;
}

export interface Sheet {
  slug: string;
  name: string;
  kind: string;
  description: string | null;
  progress: SheetProgress;
  dataset?: DatasetStatus;
}

export interface SheetProgress {
  total: number;
  completed: number;
  solved: number;
  attempted: number;
  unsolved: number;
  percent: number;
}

export interface SheetDetail extends Sheet {
  sections: { slug: string; name: string; rating_bucket: number | null; progress: SheetProgress }[];
}

export interface SheetProblem {
  problem_id: string;
  title: string;
  platform: string;
  external_id: string;
  url: string;
  rating: number | null;
  difficulty: string;
  section: string | null;
  section_name: string | null;
  status: string;
  solved_at: string | null;
  needs_review: boolean;
}

export interface Collection {
  slug: string;
  name: string;
  description: string | null;
  color: string | null;
  is_system: boolean;
  count: number;
}

export interface LevelInfo {
  level: number;
  rank: string;
  total_xp: number;
  xp_into_level: number;
  xp_for_next_level: number | null;
  xp_to_next_level: number | null;
  progress: number;
}

export interface Dashboard {
  user: { username: string; timezone: string };
  level: LevelInfo;
  streak: {
    current: number;
    longest: number;
    active_today: boolean;
    freezes_available: number;
    last_active_date: string | null;
  };
  daily_goal: { target: number; progress: number; completed: boolean };
  totals: { problems_solved: number; independent_solves: number; total_xp: number; reviews_due: number };
  difficulty: {
    average_cf_rating: number | null;
    highest_cf_rating: number | null;
    comfortable_rating: number | null;
    rating_change_30d: number | null;
  };
  volume: Record<string, number | null>;
  independence: Record<string, unknown>;
  missions: Mission[];
  recommendations: Recommendation[];
  weaknesses: Weakness[];
  has_enough_data: boolean;
  sheets: { slug: string; name: string; kind: string; percent: number; completed: number; total: number }[];
  heatmap: Heatmap;
  recent_activity: RecentActivity[];
}

export interface Mission {
  id: string;
  code: string;
  title: string;
  description: string;
  target: number;
  progress: number;
  completed: boolean;
  xp_reward: number;
}

export interface Recommendation {
  id?: string;
  problem_id: string;
  problem: {
    id: string;
    title: string;
    platform: string;
    external_id: string;
    url: string;
    rating: number | null;
    difficulty: string;
    tags: string[];
  };
  score: number;
  reason_code: string;
  reason_text: string;
  evidence: Record<string, unknown>;
  expected_xp: number;
}

export interface Weakness {
  slug: string;
  name: string;
  kind: string;
  severity: string;
  mastery: number;
  confidence: string;
  root_cause: string;
  root_cause_label: string;
  recommended_action: string;
  recommended_difficulty: string | null;
  signals: string[];
  evidence: { metric: string; value: number | string; comparison: number | string; description: string }[];
}

export interface WeaknessSummary {
  weaknesses: Weakness[];
  weakest_topic: string | null;
  strongest_topics: { name: string; slug: string; mastery: number }[];
  has_enough_data: boolean;
}

export interface Mastery {
  slug: string;
  name: string;
  kind: string;
  attempted: number;
  solved: number;
  independent: number;
  unreported: number;
  success_rate: number;
  avg_time_minutes: number | null;
  avg_rating: number | null;
  max_rating: number | null;
  mistakes: number;
  days_since_practice: number | null;
  mastery: number;
  band: string;
  confidence: string;
  components: Record<string, number>;
}

export interface Stats {
  volume: Record<string, number | null>;
  difficulty: Record<string, number | null | Record<string, number>>;
  time: Record<string, number | null>;
  independence: {
    counts: Record<string, number>;
    reported_solves: number;
    unreported_solves: number;
    independent_rate: number;
    editorial_rate: number;
    hint_rate: number;
  };
  platforms: Record<string, number>;
  mistakes: MistakeDistribution;
  success_rate: number;
  submissions: { total: number; accepted: number; acceptance_rate: number };
}

export interface MistakeDistribution {
  total: number;
  items: { type: string; label: string; count: number; share: number }[];
  implementation_count: number;
  conceptual_count: number;
  implementation_share: number;
}

export interface DifficultyProgression {
  monthly: { month: string; solved: number; average_rating: number | null; max_rating: number | null }[];
  rating_distribution: { rating: number; solved: number }[];
  comfortable_rating: number | null;
  highest_rating: number | null;
  average_rating: number | null;
}

export interface TopicTime {
  topic: string;
  slug: string;
  average_minutes: number;
  solved: number;
}

export interface Heatmap {
  start: string;
  end: string;
  days: HeatmapDay[];
  totals: { problems: number; xp: number; active_days: number; coverage: number };
}

export interface HeatmapDay {
  date: string;
  count: number;
  intensity: number;
  xp: number;
  minutes: number;
  contests: number;
  upsolves: number;
  reviews: number;
  frozen: boolean;
}

export interface DayDetail {
  date: string;
  problems: { id: string; title: string; platform: string; rating: number | null; url: string }[];
  submissions: number;
  xp: number;
  minutes: number;
  reviews: number;
  frozen: boolean;
  topics: string[];
}

export interface RecentActivity {
  problem_id: string;
  title: string;
  platform: string;
  external_id: string;
  rating: number | null;
  difficulty: string;
  url: string;
  status: string;
  solution_source: string | null;
  solved_at: string | null;
}

export interface Review {
  id: string;
  problem_id: string;
  problem: { title: string; platform: string; external_id: string; url: string; rating: number | null; difficulty: string };
  reason: string;
  reason_detail: string;
  scheduled_for: string;
  interval_days: number;
}

export interface AchievementList {
  unlocked_count: number;
  total: number;
  metrics: Record<string, number>;
  items: {
    code: string;
    name: string;
    description: string;
    category: string;
    tier: string;
    icon: string | null;
    xp_reward: number;
    unlocked: boolean;
    unlocked_at: string | null;
  }[];
}

export interface Gamification {
  level: LevelInfo;
  streak: { current: number; longest: number; active_today: boolean };
  freezes: { available: number };
  total_xp: number;
  levels: { level: number; xp_required: number; rank: string }[];
}

export interface FreezeState {
  available: number;
  transactions: { id: string; kind: string; amount: number; xp_cost: number; note: string | null; created_at: string }[];
}

export interface Contest {
  id: string;
  contest_id: string;
  name: string;
  platform: string;
  date: string | null;
  rank: number | null;
  rating_after: number | null;
  rating_change: number | null;
  solved_live: number;
  upsolved: number;
  total_solved: number;
}

export interface ContestSummary {
  count: number;
  best_rank: number | null;
  current_rating: number | null;
  max_rating: number | null;
  total_live_solves: number;
  total_upsolves: number;
  average_solved_per_contest: number;
  rating_history: { date: string | null; rating: number | null; change: number | null; name: string }[];
}

export interface SyncResult {
  platform: string;
  status: string;
  submissions_fetched: number;
  submissions_new: number;
  problems_solved: number;
  xp_awarded: number;
  error: string | null;
  last_success: string | null;
  details: Record<string, unknown>;
}

export interface SolveResult {
  first_solve: boolean;
  xp_awarded: number;
  xp_breakdown: Record<string, number>;
  streak: number;
  leveled_up: boolean;
  level: number;
  achievements_unlocked: string[];
  daily_goal: { progress: number; target: number };
}

export interface AiStatus {
  available: boolean;
  provider: string;
  model: string;
  requests_today: number;
  daily_budget: number;
  remaining: number;
  reason: string | null;
}

export interface Insight {
  id?: string;
  type: string;
  title: string;
  summary: string;
  confidence: string;
  structured_output: {
    title?: string;
    summary?: string;
    diagnosis?: string;
    evidence?: { metric: string; value: string; comparison?: string | null }[];
    recommendations?: { action: string; reason: string }[];
    metrics_used?: string[];
    weaknesses?: {
      topic: string;
      severity: string;
      evidence: string[];
      root_cause: string;
      recommended_action: string;
      recommended_difficulty?: string | null;
    }[];
    days?: { day: string; focus: string; tasks: string[] }[];
    notes?: string[];
  } | null;
  context_snapshot: Record<string, unknown> | null;
  ai_generated: boolean;
  model?: string;
  generated_at: string;
  cached?: boolean;
  stale?: boolean;
  message?: string;
  tokens?: { input: number; output: number };
}

export interface ChatResponse {
  available: boolean;
  answer: string;
  tools_used: string[];
  conversation_id?: string;
  model?: string;
}

export interface AiUsage {
  available: boolean;
  model: string;
  today: { requests: number; input_tokens: number; output_tokens: number; average_latency_ms: number };
  last_30_days: { requests: number; input_tokens: number; output_tokens: number };
  daily_budget: number;
  remaining_today: number;
  failures_last_30_days: number;
}

// ---------------------------------------------------------------------------
// ICPC mode
// ---------------------------------------------------------------------------

export interface IcpcSettings {
  target_date: string | null;
  team_name: string | null;
  weekly_practice_days: number;
  target_rating: number | null;
  focus_topics: string[];
  enabled: boolean;
  configured?: boolean;
}

export interface Countdown {
  target_date: string | null;
  days_remaining: number | null;
  weeks_remaining: number | null;
  is_past: boolean;
  practice_days_remaining?: number;
  message: string | null;
}

/**
 * A readiness component. `score === null` means "not enough evidence" and is
 * NOT the same as zero — the UI must render the two differently.
 */
export interface ReadinessComponent {
  key: string;
  name: string;
  score: number | null;
  evidence: Record<string, unknown>;
  missing: string | null;
}

export interface Readiness {
  overall: number | null;
  has_sufficient_data: boolean;
  components_answered: number;
  components_required: number;
  target_rating: number;
  target_rating_is_default: boolean;
  blocked_reason: string | null;
  components: ReadinessComponent[];
  weights: Record<string, number>;
}

export interface RoadmapNode {
  key: string;
  name: string;
  phase: string;
  topic: string;
  band: [number, number];
  why: string;
  requires: string[];
  unmet_prerequisites: string[];
  templates: string[];
  solved: number;
  attempted: number;
  mastery: number | null;
  confidence: string | null;
  days_since_practice: number | null;
  state: 'comfortable' | 'started' | 'ready' | 'blocked';
  studied: boolean;
  template_reviewed: boolean;
  self_confidence: number | null;
  notes: string | null;
}

export interface IcpcRoadmap {
  phases: { key: string; name: string; nodes: RoadmapNode[] }[];
  totals: { nodes: number; comfortable: number; started: number; ready: number; blocked: number };
}

export interface TemplateSummary {
  slug: string;
  name: string;
  topic: string;
  typing_minutes: number;
  complexity: string;
  why: string;
  reviews: number;
  last_reviewed_at: string | null;
  typed_from_memory: boolean;
}

export interface TemplateDetail {
  slug: string;
  name: string;
  topic: string;
  typing_minutes: number;
  complexity: string;
  why: string;
  pitfalls: string[];
  code: string;
  reviews: { reviewed_at: string; from_memory: boolean; seconds_taken: number | null; confidence: number | null }[];
}

export interface VirtualContestProblem {
  problem_id: string;
  label: string | null;
  position: number;
  status: string;
  wrong_attempts: number;
  solved_at_minute: number | null;
  upsolved_at: string | null;
  title: string | null;
  url: string | null;
  rating: number | null;
  platform: string | null;
}

export interface VirtualContest {
  id: string;
  name: string;
  status: string;
  duration_minutes: number;
  started_at: string;
  finished_at: string | null;
  penalty_minutes: number;
  notes: string | null;
  solved_count: number;
  problem_count: number;
  problems: VirtualContestProblem[];
}

export interface UpsolveItem {
  problem_id: string;
  title: string;
  url: string;
  rating: number | null;
  platform: string;
  contest_id: string;
  contest_name: string;
  label: string | null;
  wrong_attempts: number;
  status: string;
}

export interface IcpcDashboard {
  settings: IcpcSettings;
  countdown: Countdown;
  readiness: Readiness;
  roadmap: IcpcRoadmap;
  recent_contests: VirtualContest[];
  upsolve_queue: UpsolveItem[];
}
