"use client";

import { useEffect, useRef, useState } from "react";
import { Tooltip } from "@base-ui/react/tooltip";
import { CheckCircle2, Eye } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, cardClassName } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Combobox } from "@/components/ui/combobox";
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  ApiError,
  KNOWN_OBJECTIVES,
  type AiProvider,
  type AiProviderConfig,
  type ModelCatalog,
  type ModelInfo,
  type Workspace,
} from "@/lib/api";
import { COUNTRIES } from "@/lib/countries";
import { INDUSTRIES } from "@/lib/industries";
import { TIER_LABEL, TIER_ORDER } from "@/lib/modelTiers";
import { cn } from "@/lib/utils";

const OTHER_INDUSTRY = "Other";
const INDUSTRY_OPTIONS = [...INDUSTRIES, OTHER_INDUSTRY];

const PROVIDERS: { value: AiProvider; label: string }[] = [
  { value: "openai", label: "OpenAI" },
  { value: "google", label: "Google" },
  { value: "anthropic", label: "Anthropic" },
];

const CUSTOM = "__custom__";

function findModel(models: ModelInfo[], id: string | null | undefined): ModelInfo | undefined {
  return models.find((m) => m.id === id);
}

export default function SettingsPage() {
  const [configs, setConfigs] = useState<AiProviderConfig[] | null>(null);
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [provider, setProvider] = useState<AiProvider>("openai");
  const [apiKey, setApiKey] = useState("");
  const [selectedModelId, setSelectedModelId] = useState("");
  const [customModel, setCustomModel] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const prefilled = useRef(false);

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [objectives, setObjectives] = useState<string[]>([]);
  const [objectivesNote, setObjectivesNote] = useState("");
  const [country, setCountry] = useState<string | null>(null);
  const [industry, setIndustry] = useState<string | null>(null);
  const [industryOther, setIndustryOther] = useState("");
  const [website, setWebsite] = useState("");
  const [reportIntervalHours, setReportIntervalHours] = useState("");
  const [contextSaving, setContextSaving] = useState(false);
  const [contextError, setContextError] = useState<string | null>(null);
  const [contextSaved, setContextSaved] = useState(false);

  useEffect(() => {
    Promise.all([
      api.workspace.listAiProviders().catch(() => []),
      api.workspace.listModelCatalog().catch(() => null),
    ]).then(([configsResult, catalogResult]) => {
      setConfigs(configsResult);
      setCatalog(catalogResult);
      if (!prefilled.current) {
        prefilled.current = true;
        prefillModel("openai", configsResult, catalogResult);
      }
    });
    api.workspace.me().then((ws) => {
      setWorkspace(ws);
      setObjectives(ws.objectives_selected ?? []);
      setObjectivesNote(ws.objectives_note ?? "");
      setCountry(ws.country);
      if (ws.market && (INDUSTRIES as readonly string[]).includes(ws.market)) {
        setIndustry(ws.market);
      } else if (ws.market) {
        setIndustry(OTHER_INDUSTRY);
        setIndustryOther(ws.market);
      }
      setWebsite(ws.website ?? "");
      setReportIntervalHours(ws.report_interval_hours != null ? String(ws.report_interval_hours) : "");
    });
  }, []);

  function toggleObjective(value: string, checked: boolean) {
    setObjectives((prev) => (checked ? [...prev, value] : prev.filter((o) => o !== value)));
  }

  async function handleContextSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (objectives.length === 0) {
      setContextError("Pick at least one objective.");
      return;
    }
    if (!country) {
      setContextError("Country is required so discovery can scope results correctly.");
      return;
    }
    const resolvedIndustry = industry === OTHER_INDUSTRY ? industryOther.trim() : industry;
    setContextError(null);
    setContextSaved(false);
    setContextSaving(true);
    try {
      const updated = await api.workspace.updateContext({
        objectives_selected: objectives,
        objectives_note: objectivesNote || null,
        country,
        market: resolvedIndustry || null,
        website: website.trim() || null,
        report_interval_hours: reportIntervalHours.trim() ? Number(reportIntervalHours) : null,
      });
      setWorkspace(updated);
      setContextSaved(true);
    } catch (err) {
      setContextError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setContextSaving(false);
    }
  }

  function prefillModel(nextProvider: AiProvider, configsList: AiProviderConfig[], catalogData: ModelCatalog | null) {
    const existing = configsList.find((c) => c.provider === nextProvider);
    const models = catalogData?.[nextProvider] ?? [];
    if (existing?.model_override) {
      if (findModel(models, existing.model_override)) {
        setSelectedModelId(existing.model_override);
        setCustomModel("");
      } else {
        setSelectedModelId(CUSTOM);
        setCustomModel(existing.model_override);
      }
    } else {
      setSelectedModelId("");
      setCustomModel("");
    }
  }

  const active = configs?.find((c) => c.is_active);
  const configForProvider = configs?.find((c) => c.provider === provider);
  const models = catalog?.[provider] ?? [];
  const defaultModel = models.find((m) => m.default);
  const selectedModel = findModel(models, selectedModelId);
  const modelsByTier = TIER_ORDER.map((tier) => ({
    tier,
    models: models.filter((m) => m.tier === tier),
  })).filter((group) => group.models.length > 0);
  const apiKeyRequired = !configForProvider;

  function handleProviderChange(next: AiProvider) {
    setProvider(next);
    setApiKey("");
    setError(null);
    setSaved(false);
    prefillModel(next, configs ?? [], catalog);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (apiKeyRequired && !apiKey.trim()) {
      setError("An API key is required the first time you configure this provider.");
      return;
    }
    let modelOverride: string | null = null;
    if (selectedModelId === CUSTOM) {
      if (!customModel.trim()) {
        setError("Enter a model ID, or pick one from the list above.");
        return;
      }
      modelOverride = customModel.trim();
    } else if (selectedModelId && selectedModelId !== defaultModel?.id) {
      modelOverride = selectedModelId;
    }

    setError(null);
    setSaved(false);
    setSaving(true);
    try {
      await api.workspace.setAiProvider({
        provider,
        api_key: apiKey.trim() || undefined,
        model_override: modelOverride,
      });
      setApiKey("");
      setSaved(true);
      const fresh = await api.workspace.listAiProviders();
      setConfigs(fresh);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-8 py-10">
      <PageHeader title="Settings" description="Your AI provider key — used for catalog assist, discovery, and reports." />

      <div className="mt-6 grid grid-cols-1 items-start gap-8 lg:grid-cols-2">
      <div>
      {active && (
        <Card className="mb-6 flex items-center gap-2 text-sm">
          <CheckCircle2 className="size-4 shrink-0 text-good" />
          <span className="text-ink">
            <span className="font-medium">{PROVIDERS.find((p) => p.value === active.provider)?.label}</span> is active
            {active.model_override && <span className="text-slate"> · {active.model_override}</span>}
          </span>
        </Card>
      )}

      <form onSubmit={handleSubmit} className={cn(cardClassName, "space-y-4 p-6")}>
        <div className="space-y-1.5">
          <Label htmlFor="provider">Provider</Label>
          <Select
            id="provider"
            value={provider}
            onChange={(e) => handleProviderChange(e.target.value as AiProvider)}
            className="w-full"
          >
            {PROVIDERS.map((p) => {
              const hasConfig = configs?.some((c) => c.provider === p.value);
              return (
                <option key={p.value} value={p.value}>
                  {p.label}
                  {hasConfig ? " — configured" : ""}
                </option>
              );
            })}
          </Select>
          <p className="text-xs text-slate-soft">
            {configForProvider
              ? `Already configured${configForProvider.is_active ? " and active" : ""} — change the model below without re-entering your key, or enter a new key to rotate it.`
              : "Not configured yet — an API key is required."}
          </p>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="api-key">API key {!apiKeyRequired && <span className="font-normal text-slate-soft">(optional)</span>}</Label>
          <Input
            id="api-key"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={apiKeyRequired ? "sk-…" : "Leave blank to keep your saved key"}
            autoComplete="off"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="model">Model</Label>
          <Card className="flex items-start gap-2 p-3 text-xs text-slate">
            <Eye className="mt-0.5 size-3.5 shrink-0 text-accent" />
            <span>
              This workspace uses AI to describe product photos, so it needs a model that can <strong className="text-ink">see images (multimodal)</strong> —
              every option below supports that.
            </span>
          </Card>

          <Select
            id="model"
            value={selectedModelId || defaultModel?.id || ""}
            onChange={(e) => setSelectedModelId(e.target.value)}
            className="w-full"
          >
            {modelsByTier.map((group) => (
              <optgroup key={group.tier} label={TIER_LABEL[group.tier]}>
                {group.models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                    {m.default ? " (default)" : ""}
                  </option>
                ))}
              </optgroup>
            ))}
            <option value={CUSTOM}>Custom model ID…</option>
          </Select>

          {selectedModelId === CUSTOM ? (
            <div className="space-y-1">
              <Input
                value={customModel}
                onChange={(e) => setCustomModel(e.target.value)}
                placeholder="e.g. gpt-5.6-luna, or any model this provider serves"
              />
              <p className="text-xs text-slate-soft">
                Must support image input (multimodal) — photo-assist sends product photos to it and will fail on a text-only model.
              </p>
            </div>
          ) : (
            selectedModel && <p className="text-xs text-slate">{selectedModel.blurb}</p>
          )}
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}
        {saved && !error && <p className="text-sm text-good">Saved.</p>}

        <Button type="submit" disabled={saving} className="w-full">
          {saving ? "Saving…" : "Save"}
        </Button>
      </form>
      </div>

      <div>
      <h2 className="font-[family-name:var(--font-display)] text-xl font-semibold text-ink">Business context</h2>
      <p className="mt-1 text-sm text-slate">
        What discovery and reports are built around — set at onboarding, editable any time as your business changes.
      </p>

      {!workspace ? (
        <p className="mt-6 text-sm text-slate-soft">Loading…</p>
      ) : (
        <form onSubmit={handleContextSubmit} className={cn(cardClassName, "mt-6 space-y-6 p-6")}>
          <div className="space-y-3">
            <Label>Why are you using this platform?</Label>
            <Tooltip.Provider>
              {KNOWN_OBJECTIVES.map((o) => (
                <div key={o.value} className="flex items-center gap-2">
                  <label className="flex items-center gap-3">
                    <Checkbox
                      checked={objectives.includes(o.value)}
                      onCheckedChange={(checked) => toggleObjective(o.value, checked)}
                    />
                    <span className="text-sm text-ink">{o.label}</span>
                  </label>
                  <InfoTooltip text={o.description} />
                </div>
              ))}
            </Tooltip.Provider>
            <Textarea
              value={objectivesNote}
              onChange={(e) => setObjectivesNote(e.target.value)}
              placeholder="Anything else? (optional)"
              rows={2}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="country">Country</Label>
              <Combobox id="country" options={COUNTRIES} value={country} onValueChange={setCountry} placeholder="Search countries…" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="industry">Market / industry</Label>
              <Combobox
                id="industry"
                options={INDUSTRY_OPTIONS}
                value={industry}
                onValueChange={setIndustry}
                placeholder="Search industries…"
              />
            </div>
          </div>

          {industry === OTHER_INDUSTRY && (
            <Input value={industryOther} onChange={(e) => setIndustryOther(e.target.value)} placeholder="Describe your industry" />
          )}

          <div className="space-y-1.5">
            <Label htmlFor="context-website">Your website</Label>
            <Input
              id="context-website"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              placeholder="acme.com"
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5">
              <Label htmlFor="report-interval">Report frequency</Label>
              <InfoTooltip text="How often to automatically generate a competitor report in the background. You can always generate one manually from Reports in the meantime." />
            </div>
            <Select
              id="report-interval"
              value={reportIntervalHours}
              onChange={(e) => setReportIntervalHours(e.target.value)}
              className="w-48"
            >
              <option value="">Manual only</option>
              <option value="24">Daily</option>
              <option value="168">Weekly</option>
            </Select>
          </div>

          {contextError && <p className="text-sm text-danger">{contextError}</p>}
          {contextSaved && !contextError && <p className="text-sm text-good">Saved.</p>}

          <Button type="submit" disabled={contextSaving} className="w-full">
            {contextSaving ? "Saving…" : "Save business context"}
          </Button>
        </form>
      )}
      </div>
      </div>
    </div>
  );
}
