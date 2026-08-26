"use client";

// Interactive first-run product tour — spotlights Sidebar nav items in
// conceptual (not visual) order to explain what the app does, including
// the automated pipeline (built earlier this session) that silently runs
// discovery/matching/reporting the moment a first product lands, so a new
// user isn't left wondering how competitors/a report appeared with no
// click of their own. One-shot: Workspace.product_tour_completed_at is set
// server-side the first time this ends, by finishing OR skipping — both
// count as "seen," so it never nags a later Home visit. restart() (wired
// to a "Replay product tour" link in Settings) is purely client-side and
// deliberately never touches that persisted flag.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";

import { api, type Workspace } from "@/lib/api";

export interface TourStep {
  id: string;
  // Matches a Sidebar NavLink's data-tour attribute — absent for the
  // centered Welcome/Done cards, which have no spotlight target.
  target?: string;
  title: string;
  body: string;
}

export const TOUR_STEPS: TourStep[] = [
  {
    id: "welcome",
    title: "Welcome to Pricing Intelligence AI",
    body: "60 seconds to show you around: where things live and what runs on its own.",
  },
  {
    id: "settings",
    target: "nav-settings",
    title: "Add your AI provider key first",
    body: "Discovery, matching, and reports all depend on it. Nothing below actually runs without one configured here.",
  },
  {
    id: "catalog",
    target: "nav-catalog",
    title: "Your catalog",
    body: "Add your products here first. Everything else in the app is built around what's in your catalog.",
  },
  {
    id: "discovery",
    target: "nav-discovery",
    title: "Discovery",
    body: "Finds real competitors using AI web search. The moment you add your first product, this actually runs automatically in the background, no click needed.",
  },
  {
    id: "tracked",
    target: "nav-tracked",
    title: "Tracked",
    body: "Confirmed matches between your products and competitors, with live price comparisons.",
  },
  {
    id: "reports",
    target: "nav-reports",
    title: "Reports",
    body: "AI-written business reports: comparisons, alerts, recommendations. The first one also generates automatically once there's something to report on.",
  },
  {
    id: "activity",
    target: "nav-activity",
    title: "Activity",
    body: "Anything running in the background, including that automatic first run, shows up here live, not just the things you click yourself.",
  },
  {
    id: "done",
    title: "That's it",
    body: "You know where everything lives. Get started whenever you're ready.",
  },
];

interface ProductTourContextValue {
  active: boolean;
  step: TourStep;
  stepIndex: number;
  totalSteps: number;
  next: () => void;
  back: () => void;
  skip: () => void;
  restart: () => void;
}

const ProductTourContext = createContext<ProductTourContextValue | null>(null);

export function ProductTourProvider({
  workspace,
  children,
}: {
  workspace: Workspace | null;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [active, setActive] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  // Tracked locally, not read fresh from `workspace` on every check — that
  // prop is fetched once in app/(app)/layout.tsx and never re-fetched
  // after completeProductTour() succeeds, so relying on it directly would
  // either (a) never auto-start if the user's first page isn't Home (the
  // effect below has to re-run every time pathname changes to catch a
  // later visit to Home, which means it needs a value that's actually
  // current) or (b) re-trigger the tour every time they return to Home
  // later in the same session, since the stale prop would still read null.
  const [dismissed, setDismissed] = useState(() => workspace?.product_tour_completed_at != null);

  useEffect(() => {
    if (workspace?.product_tour_completed_at != null) setDismissed(true);
  }, [workspace?.product_tour_completed_at]);

  // Re-checked on every pathname change (not just once on mount) so a
  // user who lands somewhere other than Home first still gets the tour
  // the moment they actually visit it.
  useEffect(() => {
    if (workspace && !dismissed && pathname === "/") {
      setStepIndex(0);
      setActive(true);
    }
  }, [workspace, dismissed, pathname]);

  const complete = useCallback(() => {
    setActive(false);
    setDismissed(true);
    api.workspace.completeProductTour().catch(() => {});
  }, []);

  const next = useCallback(() => {
    setStepIndex((i) => {
      if (i >= TOUR_STEPS.length - 1) {
        complete();
        return i;
      }
      return i + 1;
    });
  }, [complete]);

  const back = useCallback(() => {
    setStepIndex((i) => Math.max(0, i - 1));
  }, []);

  const skip = useCallback(() => {
    complete();
  }, [complete]);

  const restart = useCallback(() => {
    setStepIndex(0);
    setActive(true);
  }, []);

  const value = useMemo<ProductTourContextValue>(
    () => ({
      active,
      step: TOUR_STEPS[stepIndex],
      stepIndex,
      totalSteps: TOUR_STEPS.length,
      next,
      back,
      skip,
      restart,
    }),
    [active, stepIndex, next, back, skip, restart]
  );

  return <ProductTourContext.Provider value={value}>{children}</ProductTourContext.Provider>;
}

export function useProductTour(): ProductTourContextValue {
  const ctx = useContext(ProductTourContext);
  if (!ctx) throw new Error("useProductTour must be used within a ProductTourProvider");
  return ctx;
}
