"use client";

import { useEffect, useState } from "react";
import { CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  api,
  ApiError,
  type AiProvider,
  type AiProviderConfig,
  type ModelCatalog,
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

const TIER_CLASS: Record<ModelTier, string> = {
  low: "bg-good/10 text-good",
  medium: "bg-slate/10 text-slate",
  high: "bg-accent/10 text-accent",
};

const CUSTOM = "__custom__";

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

  useEffect(() => {
    api.workspace.listAiProviders().then(setConfigs).catch(() => setConfigs([]));
    api.workspace.listModelCatalog().then(setCatalog).catch(() => setCatalog(null));
  }, []);

  const active = configs?.find((c) => c.is_active);
  const models = catalog?.[provider] ?? [];
  const defaultModel = models.find((m) => m.default);
  const modelsByTier = TIER_ORDER.map((tier) => ({
    tier,
    models: models.filter((m) => m.tier === tier),
  })).filter((group) => group.models.length > 0);

  function handleProviderChange(next: AiProvider) {
    setProvider(next);
    setSelectedModelId("");
    setCustomModel("");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!apiKey.trim()) {
      setError("API key is required.");
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
        api_key: apiKey.trim(),
        model_override: modelOverride,
      });
      setApiKey("");
      setSelectedModelId("");
      setCustomModel("");
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
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="api-key">API key</Label>
          <Input
            id="api-key"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-…"
            autoComplete="off"
          />
        </div>

        <div className="space-y-1.5">
          <Label>Model</Label>
          <p className="text-xs text-slate-soft">A wide range, low to high cost — pick whichever fits, not just the default.</p>
          <div className="space-y-3">
            {modelsByTier.map((group) => (
              <div key={group.tier} className="space-y-1">
                <p className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${TIER_CLASS[group.tier]}`}>
                  {TIER_LABEL[group.tier]}
                </p>
                <div className="space-y-1">
                  {group.models.map((m) => {
                    const isSelected = selectedModelId === m.id || (!selectedModelId && m.default);
                    return (
                      <label
                        key={m.id}
                        className={`flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2 transition-colors ${
                          isSelected ? "border-accent bg-accent/5" : "border-border hover:border-slate-soft"
                        }`}
                      >
                        <input
                          type="radio"
                          name="model"
                          className="mt-1 accent-[var(--accent)]"
                          checked={isSelected}
                          onChange={() => setSelectedModelId(m.id)}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-ink">{m.label}</span>
                            {m.default && <span className="text-xs text-slate-soft">Default</span>}
                          </div>
                          <p className="mt-0.5 text-xs text-slate">{m.blurb}</p>
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}

            <label
              className={`flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2.5 transition-colors ${
                selectedModelId === CUSTOM ? "border-accent bg-accent/5" : "border-border hover:border-slate-soft"
              }`}
            >
              <input
                type="radio"
                name="model"
                className="accent-[var(--accent)]"
                checked={selectedModelId === CUSTOM}
                onChange={() => setSelectedModelId(CUSTOM)}
              />
              <span className="text-sm font-medium text-ink">Custom model ID</span>
            </label>
            {selectedModelId === CUSTOM && (
              <Input
                value={customModel}
                onChange={(e) => setCustomModel(e.target.value)}
                placeholder="e.g. gpt-5.6-luna, or any model this provider serves"
                className="ml-7 w-[calc(100%-1.75rem)]"
              />
            )}
          </div>
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
