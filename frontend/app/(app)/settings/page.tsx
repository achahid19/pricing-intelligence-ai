"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Eye } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  api,
  ApiError,
  type AiProvider,
  type AiProviderConfig,
  type ModelCatalog,
  type ModelInfo,
  type ModelTier,
} from "@/lib/api";

const PROVIDERS: { value: AiProvider; label: string }[] = [
  { value: "openai", label: "OpenAI" },
  { value: "google", label: "Google" },
  { value: "anthropic", label: "Anthropic" },
  { value: "openrouter", label: "OpenRouter" },
];

const TIER_ORDER: ModelTier[] = ["low", "medium", "high"];

const TIER_LABEL: Record<ModelTier, string> = {
  low: "Low cost",
  medium: "Medium cost",
  high: "High cost",
};

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
  }, []);

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
    <div className="mx-auto max-w-2xl px-8 py-10">
      <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-ink">Settings</h1>
      <p className="mt-1 text-sm text-slate">Your AI provider key — used for catalog assist, discovery, and reports.</p>

      {active && (
        <div className="mt-6 flex items-center gap-2 rounded-lg border border-border bg-paper-raised px-4 py-3 text-sm">
          <CheckCircle2 className="size-4 shrink-0 text-good" />
          <span className="text-ink">
            <span className="font-medium">{PROVIDERS.find((p) => p.value === active.provider)?.label}</span> is active
            {active.model_override && <span className="text-slate"> · {active.model_override}</span>}
          </span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="mt-6 space-y-4 rounded-lg border border-border bg-paper-raised p-6">
        <div className="space-y-1.5">
          <Label htmlFor="provider">Provider</Label>
          <select
            id="provider"
            value={provider}
            onChange={(e) => handleProviderChange(e.target.value as AiProvider)}
            className="h-10 w-full rounded-md border border-border bg-paper px-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/20"
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
          </select>
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
          <div className="flex items-start gap-2 rounded-md border border-border bg-paper px-3 py-2 text-xs text-slate">
            <Eye className="mt-0.5 size-3.5 shrink-0 text-accent" />
            <span>
              This workspace uses AI to describe product photos, so it needs a model that can <strong className="text-ink">see images (multimodal)</strong> —
              every option below supports that.
            </span>
          </div>

          <select
            id="model"
            value={selectedModelId || defaultModel?.id || ""}
            onChange={(e) => setSelectedModelId(e.target.value)}
            className="h-10 w-full rounded-md border border-border bg-paper px-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/20"
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
          </select>

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
  );
}
