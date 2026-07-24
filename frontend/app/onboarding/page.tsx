"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError, KNOWN_OBJECTIVES } from "@/lib/api";

export default function OnboardingPage() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [objectives, setObjectives] = useState<string[]>([]);
  const [objectivesNote, setObjectivesNote] = useState("");
  const [country, setCountry] = useState("");
  const [market, setMarket] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.workspace
      .me()
      .then((workspace) => {
        if (workspace.onboarding_completed) router.replace("/");
        else setChecking(false);
      })
      .catch(() => router.replace("/login"));
  }, [router]);

  function toggleObjective(value: string, checked: boolean) {
    setObjectives((prev) => (checked ? [...prev, value] : prev.filter((o) => o !== value)));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (objectives.length === 0) {
      setError("Pick at least one objective — or add your own below.");
      return;
    }
    if (!country.trim()) {
      setError("Country is required so discovery can scope results correctly.");
      return;
    }
    setLoading(true);
    try {
      await api.workspace.updateContext({
        objectives_selected: objectives,
        objectives_note: objectivesNote || null,
        country: country.trim(),
        market: market.trim() || null,
      });
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  if (checking) return null;

  return (
    <div className="mx-auto max-w-lg px-6 py-16">
      <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-ink">
        Tell us about your business
      </h1>
      <p className="mt-2 text-sm text-slate">
        This shapes what the AI looks for and how it reports back — nothing here is locked in, you can change it later in Settings.
      </p>

      <form onSubmit={handleSubmit} className="mt-8 space-y-6">
        <div className="space-y-3">
          <Label>Why are you using this platform?</Label>
          {KNOWN_OBJECTIVES.map((o) => (
            <label key={o.value} className="flex items-center gap-3">
              <Checkbox
                checked={objectives.includes(o.value)}
                onCheckedChange={(checked) => toggleObjective(o.value, checked)}
              />
              <span className="text-sm text-ink">{o.label}</span>
            </label>
          ))}
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
            <Input
              id="country"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              placeholder="Morocco"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="market">Market / industry</Label>
            <Input
              id="market"
              value={market}
              onChange={(e) => setMarket(e.target.value)}
              placeholder="Consumer electronics"
            />
          </div>
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <Button type="submit" disabled={loading} className="w-full">
          {loading ? "Saving…" : "Continue"}
        </Button>
      </form>
    </div>
  );
}
