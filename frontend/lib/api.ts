const TOKEN_KEY = "pia_token";

// JWT stored in localStorage — simplest standard fit for a stateless-JWT
// setup (see docs/DECISIONS.md for the tradeoff vs. httpOnly cookies).
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(`/api/v1${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      // FastAPI's own HTTPException(detail="...") gives a plain string;
      // its automatic Pydantic validation errors give an array of
      // {loc, msg, type} objects instead — handle both shapes.
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        detail = body.detail.map((e: { msg?: string }) => e.msg).filter(Boolean).join("; ") || detail;
      }
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface Workspace {
  id: number;
  name: string;
  objectives_selected: string[] | null;
  objectives_note: string | null;
  country: string | null;
  market: string | null;
  website: string | null;
  report_interval_hours: number | null;
  onboarding_completed: boolean;
  created_at: string;
}

export interface WorkspaceContextUpdate {
  objectives_selected?: string[];
  objectives_note?: string | null;
  country?: string;
  market?: string | null;
  website?: string | null;
  report_interval_hours?: number | null;
}

export const KNOWN_OBJECTIVES: { value: string; label: string; description: string }[] = [
  {
    value: "market_research",
    label: "Market research",
    description: "See who your competitors are, what they sell, and how they're positioned — no price tracking required.",
  },
  {
    value: "price_alignment",
    label: "Price alignment",
    description: "Compare your prices against competitors on an ongoing basis and get alerted when you're out of line.",
  },
  {
    value: "map_compliance",
    label: "Reseller pricing compliance (MAP)",
    description: "Monitor whether resellers are advertising below the minimum price you've set for them.",
  },
];

export interface Product {
  id: number;
  name: string;
  price: string;
  currency: string;
  min_price: string | null;
  image_url: string | null;
  description: string | null;
  sku: string | null;
  brand: string | null;
  category: string | null;
  barcode: string | null;
  import_source: string;
  created_at: string;
  updated_at: string;
}

export interface ProductCreate {
  name: string;
  price: number;
  currency?: string;
  min_price?: number | null;
  image_url?: string | null;
  description?: string | null;
  sku?: string | null;
  brand?: string | null;
  category?: string | null;
  barcode?: string | null;
}

export interface ImportResult {
  created: number;
  skipped: string[];
  errors: string[];
}

export interface AiDescribeResult {
  title: string;
  description: string;
  category: string | null;
  image_url: string;
}

export type AiProvider = "openai" | "google" | "anthropic";

export type ModelTier = "low" | "medium" | "high";

export interface ModelInfo {
  id: string;
  label: string;
  tier: ModelTier;
  blurb: string;
  vision: boolean;
  default?: boolean;
}

export type ModelCatalog = Record<AiProvider, ModelInfo[]>;

export interface AiProviderConfig {
  id: number;
  provider: AiProvider;
  model_override: string | null;
  is_active: boolean;
  created_at: string;
}

export type CompetitorSiteStatus = "candidate" | "saved" | "dismissed";
export type DiscoveryMode = "competitor" | "reseller";

export interface CompetitorSite {
  id: number;
  workspace_id: number;
  discovery_run_id: number | null;
  domain: string;
  name: string | null;
  relationship_type: DiscoveryMode;
  confidence_score: number | null;
  rationale: string | null;
  estimated_product_count: number | null;
  status: CompetitorSiteStatus;
}

export interface DiscoveryRun {
  id: number;
  workspace_id: number;
  triggered_at: string;
  ai_provider: string;
  model: string;
  mode: DiscoveryMode;
  status: "running" | "completed" | "failed";
  error_message: string | null;
  search_count: number | null;
  skipped_known_count: number | null;
  context_snapshot: { context: string; max_candidates: number };
  sites: CompetitorSite[];
}

export interface CompetitorProduct {
  id: number;
  workspace_id: number;
  competitor_site_id: number;
  title: string;
  price: string | null;
  currency: string | null;
  url: string;
  image_url: string | null;
  description: string | null;
  stock_status: string | null;
  additional_info: string | null;
  is_trackable: boolean;
  discovered_at: string;
  updated_at: string;
}

export type ProductMatchStatus = "candidate" | "confirmed" | "dismissed";

export interface ProductMatch {
  id: number;
  workspace_id: number;
  product_id: number;
  competitor_product_id: number;
  match_method: "manual" | "ai_auto";
  confidence: number | null;
  rationale: string | null;
  status: ProductMatchStatus;
  created_at: string;
}

// Flat, denormalized view of one confirmed (or other-status) ProductMatch
// for the workspace-wide Tracked page — joins in enough from
// Product/CompetitorProduct/CompetitorSite server-side that the frontend
// needs no further per-id lookups.
export interface TrackedMatch {
  id: number;
  status: ProductMatchStatus;
  match_method: "manual" | "ai_auto";
  confidence: number | null;
  rationale: string | null;
  created_at: string;
  product_id: number;
  product_name: string;
  product_price: string;
  product_currency: string;
  product_min_price: string | null;
  competitor_product_id: number;
  competitor_product_title: string;
  competitor_product_price: string | null;
  competitor_product_currency: string | null;
  competitor_product_is_trackable: boolean;
  competitor_product_updated_at: string;
  competitor_site_id: number;
  competitor_site_domain: string;
  competitor_site_name: string | null;
  competitor_site_relationship_type: DiscoveryMode;
}

export interface TrendInfo {
  previous_price: number;
  previous_checked_at: string;
  direction: "up" | "down" | "same";
  delta_pct: number;
  is_anomaly: boolean;
}

export interface PriceComparisonRow {
  match_id: number;
  match_method: "manual" | "ai_auto";
  confidence: number | null;
  rationale: string | null;
  product_id: number;
  product_name: string;
  product_price: number;
  product_currency: string;
  product_min_price: number | null;
  competitor_product_id: number;
  competitor_product_title: string;
  competitor_product_price: number | null;
  competitor_product_currency: string | null;
  competitor_product_is_trackable: boolean;
  competitor_site_id: number;
  competitor_site_domain: string;
  competitor_site_name: string | null;
  competitor_site_relationship_type: DiscoveryMode;
  same_currency: boolean;
  price_delta_pct: number | null;
  below_map: boolean;
  trend: TrendInfo | null;
}

export interface AlertItem extends PriceComparisonRow {
  type: "map_violation" | "price_anomaly";
  severity: "high" | "medium";
  message: string;
}

// Same-currency-gated comparison metrics for one product (see
// backend/app/reporting/metrics.py). Nulls/zeros when zero same-currency
// competitor prices exist. "N of total" must always use
// same_currency_competitors_count + 1 as the denominator, never
// total_competitors_compared + 1 — the two differ whenever any match is
// cross-currency.
export interface ProductMetrics {
  price_rank: number | null;
  total_competitors_compared: number;
  same_currency_competitors_count: number;
  sellers_cheaper: number;
  price_index: number | null;
  cheapest_competitor_name: string | null;
  cheapest_competitor_price: number | null;
}

export interface ProductComparisonGroup {
  product_id: number;
  product_name: string;
  product_price: number;
  product_currency: string;
  product_min_price: number | null;
  metrics: ProductMetrics;
  matches: PriceComparisonRow[];
}

export interface UnmatchedCompetitorProduct {
  competitor_product_id: number;
  title: string;
  price: number | null;
  currency: string | null;
  description: string | null;
}

export interface SiteCoverage {
  competitor_site_id: number;
  competitor_site_domain: string;
  competitor_site_name: string | null;
  relationship_type: DiscoveryMode;
  total_products_discovered: number;
  matched_products_count: number;
  unmatched_sample: UnmatchedCompetitorProduct[];
}

export interface MarketCoverage {
  own_catalog_size: number;
  own_products_with_confirmed_match: number;
  total_competitor_products_discovered: number;
  sites: SiteCoverage[];
}

export interface SummaryStats {
  matches_tracked: number;
  alerts_count: number;
  map_violations_count: number;
  price_anomalies_count: number;
  price_increases: number;
  price_decreases: number;
  no_price_count: number;
}

export interface ReportContent {
  schema_version: number;
  summary_stats: SummaryStats;
  price_comparison: ProductComparisonGroup[];
  market_coverage: MarketCoverage;
  alerts: AlertItem[];
  executive_summary: string | null;
  market_position: string | null;
  competitive_gaps: string | null;
  recommendations: { objective: string; text: string }[];
}

export interface CompetitorReport {
  id: number;
  workspace_id: number;
  fed_forward_from_report_id: number | null;
  generated_at: string;
  trigger_source: "manual" | "scheduled";
  ai_provider: string;
  model: string;
  status: "completed" | "failed";
  error_message: string | null;
  content: ReportContent;
}

export const api = {
  auth: {
    async signup(email: string, password: string, workspaceName: string) {
      const res = await request<TokenResponse>("/auth/signup", {
        method: "POST",
        body: JSON.stringify({ email, password, workspace_name: workspaceName }),
      });
      setToken(res.access_token);
      return res;
    },
    async login(email: string, password: string) {
      const res = await request<TokenResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setToken(res.access_token);
      return res;
    },
  },
  workspace: {
    me: () => request<Workspace>("/workspace/me"),
    updateContext: (payload: WorkspaceContextUpdate) =>
      request<Workspace>("/workspace/me", { method: "PATCH", body: JSON.stringify(payload) }),
    listModelCatalog: () => request<ModelCatalog>("/workspace/models"),
    listAiProviders: () => request<AiProviderConfig[]>("/workspace/ai-provider"),
    setAiProvider: (payload: { provider: AiProvider; api_key?: string; model_override?: string | null }) =>
      request<AiProviderConfig>("/workspace/ai-provider", { method: "POST", body: JSON.stringify(payload) }),
  },
  products: {
    list: () => request<Product[]>("/products"),
    create: (payload: ProductCreate) =>
      request<Product>("/products", { method: "POST", body: JSON.stringify(payload) }),
    update: (id: number, payload: Partial<ProductCreate>) =>
      request<Product>(`/products/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
    delete: (id: number) => request<void>(`/products/${id}`, { method: "DELETE" }),
    templateUrl: "/api/v1/products/import/template",
    async importFile(file: File): Promise<ImportResult> {
      // Bypasses the shared request() helper — it always sets
      // Content-Type: application/json, but a multipart upload needs the
      // browser to set its own Content-Type with the correct boundary.
      const token = getToken();
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/v1/products/import", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: formData,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : res.statusText);
      }
      return res.json();
    },
    async aiDescribe(file: File): Promise<AiDescribeResult> {
      // Same multipart-bypass reasoning as importFile above.
      const token = getToken();
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/v1/products/ai-describe", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: formData,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : res.statusText);
      }
      return res.json();
    },
  },
  discovery: {
    createRun: (maxCandidates: number, mode: DiscoveryMode = "competitor") =>
      request<DiscoveryRun>("/discovery/runs", {
        method: "POST",
        body: JSON.stringify({ max_candidates: maxCandidates, mode }),
      }),
    listRuns: (mode?: DiscoveryMode) => request<DiscoveryRun[]>(`/discovery/runs${mode ? `?mode=${mode}` : ""}`),
    getRun: (id: number) => request<DiscoveryRun>(`/discovery/runs/${id}`),
    updateSite: (id: number, status: CompetitorSiteStatus) =>
      request<CompetitorSite>(`/discovery/sites/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
    listSites: (siteStatus?: CompetitorSiteStatus, relationshipType?: DiscoveryMode) => {
      const params = new URLSearchParams();
      if (siteStatus) params.set("site_status", siteStatus);
      if (relationshipType) params.set("relationship_type", relationshipType);
      const qs = params.toString();
      return request<CompetitorSite[]>(`/discovery/sites${qs ? `?${qs}` : ""}`);
    },
    createSite: (domain: string, name?: string, relationshipType: DiscoveryMode = "competitor") =>
      request<CompetitorSite>("/discovery/sites", {
        method: "POST",
        body: JSON.stringify({ domain, name, relationship_type: relationshipType }),
      }),
    getSite: (siteId: number) => request<CompetitorSite>(`/discovery/sites/${siteId}`),
    discoverProducts: (siteId: number, maxProducts: number) =>
      request<CompetitorProduct[]>(`/discovery/sites/${siteId}/products`, {
        method: "POST",
        body: JSON.stringify({ max_products: maxProducts }),
      }),
    listProducts: (siteId: number) => request<CompetitorProduct[]>(`/discovery/sites/${siteId}/products`),
    autoMatch: (siteId: number) =>
      request<ProductMatch[]>(`/discovery/sites/${siteId}/auto-match`, { method: "POST" }),
    listMatches: (siteId: number) => request<ProductMatch[]>(`/discovery/sites/${siteId}/matches`),
    createMatch: (productId: number, competitorProductId: number) =>
      request<ProductMatch>("/discovery/matches", {
        method: "POST",
        body: JSON.stringify({ product_id: productId, competitor_product_id: competitorProductId }),
      }),
    updateMatch: (matchId: number, status: "confirmed" | "dismissed") =>
      request<ProductMatch>(`/discovery/matches/${matchId}`, { method: "PATCH", body: JSON.stringify({ status }) }),
    listTrackedMatches: (status: ProductMatchStatus = "confirmed") =>
      request<TrackedMatch[]>(`/discovery/matches?status_filter=${status}`),
  },
  reporting: {
    create: () => request<CompetitorReport>("/reporting/reports", { method: "POST" }),
    list: () => request<CompetitorReport[]>("/reporting/reports"),
    get: (id: number) => request<CompetitorReport>(`/reporting/reports/${id}`),
    exportUrl: (id: number) => `/api/v1/reporting/reports/${id}/export.csv`,
  },
};
