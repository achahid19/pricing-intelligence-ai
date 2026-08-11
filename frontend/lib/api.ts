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
  refresh_before_report: boolean | null;
  // Set once the automated onboarding pipeline has fired for this
  // workspace's first-ever product — null until then, never reset.
  onboarding_pipeline_triggered_at: string | null;
  // Live status of the most recent automated pipeline run (see
  // lib/pipelineStatus.tsx) — "running"|"completed"|"failed"|null.
  pipeline_status: string | null;
  pipeline_trigger_source: string | null;
  pipeline_started_at: string | null;
  pipeline_finished_at: string | null;
  pipeline_error_message: string | null;
  pipeline_report_id: number | null;
  // Per-step plan/progress for the current (or last) run — structurally
  // compatible with lib/activity.tsx's ActivityChild on purpose, so
  // pipelineStatus.tsx can pass this straight through as an entry's
  // children with no reshaping.
  pipeline_substeps: { id: string; label: string; status: "pending" | "done" | "error" }[] | null;
  // Set the first time the interactive first-run tour (lib/productTour.tsx)
  // ends, by finishing or explicitly skipping — never reset by that alone.
  product_tour_completed_at: string | null;
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
  refresh_before_report?: boolean | null;
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
  // Nullable: not every source has a price upfront (e.g. website-import
  // from a site that doesn't publish one) — addable later via edit.
  price: string | null;
  currency: string;
  min_price: string | null;
  image_url: string | null;
  description: string | null;
  sku: string | null;
  brand: string | null;
  category: string | null;
  barcode: string | null;
  import_source: string;
  // The exact page a website-imported product was found on — null for
  // every other import_source.
  source_url: string | null;
  // true = confirmed real (at discovery time, or the user corrected it
  // themselves); false = positively known bad (e.g. shared by several
  // unrelated products); null = no signal either way, not a red flag.
  source_url_verified: boolean | null;
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
  // Update-only in practice (manual creation has nothing to set this
  // from) — editable so a wrong/generic website-import link can be
  // corrected by hand.
  source_url?: string | null;
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

export interface WebsiteImportCandidate {
  title: string;
  // null when the site didn't publish a price (B2B, quote-based, brand
  // sites that route to retailers) — still shown for review, not dropped;
  // the user can type in a real/internal price before importing it.
  price: string | null;
  currency: string | null;
  url: string;
  // True when `url` is actually confirmed real (AI citation or a real
  // HTTP reachability check) — not just a string the model wrote into its
  // own JSON output, which can be an inferred/never-fetched guess.
  url_verified: boolean;
  description: string | null;
  stock_status: string | null;
  additional_info: string | null;
}

export interface WebsiteImportDiscoverResult {
  domain: string;
  candidates: WebsiteImportCandidate[];
  no_price_count: number;
  // Excluded from `candidates` entirely — products whose name already
  // exists in the catalog, so re-running discovery only shows new ones.
  already_imported_count: number;
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
  // True when `url` was actually confirmed real — either cited by the AI's
  // own web search tool, or (citation coverage is sparse in practice) a
  // real HTTP reachability check. False on rows discovered before this
  // field existed — never re-verified, not necessarily actually broken.
  is_url_verified: boolean;
  // "Not interested" — excluded from matching, market coverage, and
  // reports; a future discovery re-run leaves it alone rather than
  // reviving it. Distinct from a hard delete: restorable via updateProduct.
  is_dismissed: boolean;
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
  product_price: string | null;
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
  // Free-text, AI-observed — ambient display only, no fixed vocabulary.
  competitor_product_stock_status: string | null;
  competitor_site_id: number;
  competitor_site_domain: string;
  competitor_site_name: string | null;
  competitor_site_relationship_type: DiscoveryMode;
  same_currency: boolean;
  price_delta_pct: number | null;
  below_map: boolean;
  trend: TrendInfo | null;
}

// Not every alert is about one specific confirmed match, or even about a
// competitor at all: map_violation and price_anomaly are match-scoped
// (every PriceComparisonRow field below is set); new_competitor_product is
// scoped to a competitor site's whole catalog (none of your own products
// involved); own_price_change is scoped to one of YOUR OWN products with
// no competitor involved at all — competitor_site_id/domain/name are null
// for that type, which is why they're optional here.
export interface AlertItem {
  type: "map_violation" | "price_anomaly" | "new_competitor_product" | "own_price_change" | "stock_status_change";
  severity: "high" | "medium";
  message: string;
  competitor_site_id?: number | null;
  competitor_site_domain?: string | null;
  competitor_site_name?: string | null;

  match_id?: number | null;
  match_method?: "manual" | "ai_auto" | null;
  confidence?: number | null;
  rationale?: string | null;
  product_id?: number | null;
  product_name?: string | null;
  product_price?: number | null;
  product_currency?: string | null;
  product_min_price?: number | null;
  competitor_product_id?: number | null;
  competitor_product_title?: string | null;
  competitor_product_price?: number | null;
  competitor_product_currency?: string | null;
  competitor_product_is_trackable?: boolean | null;
  competitor_site_relationship_type?: DiscoveryMode | null;
  same_currency?: boolean | null;
  price_delta_pct?: number | null;
  below_map?: boolean | null;
  trend?: TrendInfo | null;

  new_product_count?: number | null;
  new_product_titles?: string[] | null;

  // stock_status_change only
  previous_stock_status?: string | null;
  current_stock_status?: string | null;
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
  price_position_summary: string | null;
  cheapest_competitor_name: string | null;
  cheapest_competitor_price: number | null;
  cheapest_competitor_site_id: number | null;
}

export interface ProductComparisonGroup {
  product_id: number;
  product_name: string;
  product_price: number;
  product_currency: string;
  product_min_price: number | null;
  // Your own price's trend since the previous report — product-level, not
  // per-match. Null on a first report or when the price hasn't changed.
  own_trend: TrendInfo | null;
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
  name: string | null;
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
    completeProductTour: () => request<Workspace>("/workspace/product-tour-complete", { method: "POST" }),
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
    deleteAll: () => request<{ deleted: number }>("/products", { method: "DELETE" }),
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
    discoverFromWebsite: (url?: string) =>
      request<WebsiteImportDiscoverResult>("/products/website-import/discover", {
        method: "POST",
        body: JSON.stringify({ url: url || null }),
      }),
    confirmWebsiteImport: (products: WebsiteImportCandidate[]) =>
      request<ImportResult>("/products/website-import/confirm", {
        method: "POST",
        body: JSON.stringify({ products }),
      }),
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
    deleteSite: (id: number) => request<void>(`/discovery/sites/${id}`, { method: "DELETE" }),
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
    updateProduct: (productId: number, isDismissed: boolean) =>
      request<CompetitorProduct>(`/discovery/products/${productId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_dismissed: isDismissed }),
      }),
    deleteProduct: (productId: number) => request<void>(`/discovery/products/${productId}`, { method: "DELETE" }),
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
    // Kicks off the full pipeline in the background (fresh product
    // discovery + auto-match for every saved competitor, then the report)
    // and returns immediately — there's no report id yet at this point.
    // Workspace.pipeline_status/pipeline_substeps (see lib/pipelineStatus.tsx)
    // is what actually carries this forward, same as the other two
    // trigger points (onboarding, scheduled).
    create: () => request<{ detail: string }>("/reporting/reports", { method: "POST" }),
    list: () => request<CompetitorReport[]>("/reporting/reports"),
    get: (id: number) => request<CompetitorReport>(`/reporting/reports/${id}`),
    delete: (id: number) => request<void>(`/reporting/reports/${id}`, { method: "DELETE" }),
    rename: (id: number, name: string) =>
      request<CompetitorReport>(`/reporting/reports/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
    // Bypasses the shared request() helper — a PDF response isn't JSON, and
    // a plain <a href> can't carry the Bearer auth header, so this fetches
    // the bytes directly and triggers the download via a synthetic anchor.
    async downloadPdf(id: number, filenameHint?: string): Promise<void> {
      const token = getToken();
      const res = await fetch(`/api/v1/reporting/reports/${id}/export.pdf`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : res.statusText);
      }
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const filenameMatch = disposition.match(/filename="([^"]+)"/);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filenameMatch?.[1] ?? filenameHint ?? `report_${id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    },
  },
};
