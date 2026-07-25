"use client";

import { useEffect, useState } from "react";
import { CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError, type AiProvider, type AiProviderConfig } from "@/lib/api";

const PROVIDERS: { value: AiProvider; label: string }[] = [
  { value: "openai", label: "OpenAI" },
  { value: "google", label: "Google" },
  { value: "anthropic", label: "Anthropic" },
];

export default function SettingsPage() {
  const [configs, setConfigs] = useState<AiProviderConfig[] | null>(null);
  const [provider, setProvider] = useState<AiProvider>("openai");
  const [apiKey, setApiKey] = useState("");
  const [modelOverride, setModelOverride] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.workspace.listAiProviders().then(setConfigs).catch(() => setConfigs([]));
  }, []);

  const active = configs?.find((c) => c.is_active);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!apiKey.trim()) {
      setError("API key is required.");
      return;
    }
    setError(null);
    setSaved(false);
    setSaving(true);
    try {
      await api.workspace.setAiProvider({
        provider,
        api_key: apiKey.trim(),
        model_override: modelOverride.trim() || null,
      });
      setApiKey("");
      setModelOverride("");
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
            onChange={(e) => setProvider(e.target.value as AiProvider)}
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
          <Label htmlFor="model-override">Model override (optional)</Label>
          <Input
            id="model-override"
            value={modelOverride}
            onChange={(e) => setModelOverride(e.target.value)}
            placeholder="Leave blank to use the default model"
          />
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
