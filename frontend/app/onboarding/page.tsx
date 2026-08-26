"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Tooltip } from "@base-ui/react/tooltip";

import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Combobox } from "@/components/ui/combobox";
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError, KNOWN_OBJECTIVES } from "@/lib/api";
import { COUNTRIES } from "@/lib/countries";
import { INDUSTRIES } from "@/lib/industries";

const OTHER_INDUSTRY = "Other";
const INDUSTRY_OPTIONS = [...INDUSTRIES, OTHER_INDUSTRY];

export default function OnboardingPage() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [objectives, setObjectives] = useState<string[]>([]);
  const [objectivesNote, setObjectivesNote] = useState("");
  const [country, setCountry] = useState<string | null>(null);
  const [industry, setIndustry] = useState<string | null>(null);
  const [industryOther, setIndustryOther] = useState("");
  const [website, setWebsite] = useState("");
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
      setError("Pick at least one objective, or add your own below.");
      return;
    }
    if (!country) {
      setError("Country is required so discovery can scope results correctly.");
      return;
    }
    const resolvedIndustry = industry === OTHER_INDUSTRY ? industryOther.trim() : industry;
    setLoading(true);
    try {
      await api.workspace.updateContext({
        objectives_selected: objectives,
        objectives_note: objectivesNote || null,
        country,
        market: resolvedIndustry || null,
        website: website.trim() || null,
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
    <div className="relative mx-auto max-w-lg px-6 py-16">
      <ThemeToggle className="absolute top-6 right-6 inline-flex size-9 items-center justify-center rounded-md text-slate transition-colors hover:bg-black/[0.04] hover:text-ink" />
      <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-ink">
        Tell us about your business
      </h1>
      <p className="mt-2 text-sm text-slate">
        This shapes what the AI looks for and how it reports back. Nothing here is locked in, you can change it later in Settings.
      </p>

      <form onSubmit={handleSubmit} className="mt-8 space-y-6">
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
            <Combobox
              id="country"
              options={COUNTRIES}
              value={country}
              onValueChange={setCountry}
              placeholder="Search countries…"
            />
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
          <Input
            value={industryOther}
            onChange={(e) => setIndustryOther(e.target.value)}
            placeholder="Describe your industry"
          />
        )}

        <div className="space-y-1.5">
          <Label htmlFor="website">Your website (optional)</Label>
          <Input
            id="website"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
            placeholder="acme.com"
          />
          <p className="text-xs text-slate-soft">
            Gives the AI real context about your business. Later, this also lets it read your own catalog automatically.
          </p>
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <Button type="submit" disabled={loading} className="w-full">
          {loading ? "Saving…" : "Continue"}
        </Button>
      </form>
    </div>
  );
}
