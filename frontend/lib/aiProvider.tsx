"use client";

// Whether the workspace has an active AI provider configured — every AI
// feature (discovery, matching, reports, ai-describe, website-import
// discover) 400s server-side without one, and until now the only way a
// user found out was by clicking the action and reading the resulting
// error text. Fetched once here (mirrors ActivityProvider's placement in
// app/(app)/layout.tsx) so every page can proactively prompt "set one up
// in Settings" instead, and disable the action outright rather than
// letting it fail. refresh() lets Settings pull the status forward the
// moment a key is saved, without a full page reload.
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api } from "@/lib/api";

interface AiProviderStatusValue {
  // null while the initial check is still in flight — deliberately
  // distinct from false, so a page can avoid flashing the "set one up"
  // prompt for a moment before the real answer arrives.
  hasActiveProvider: boolean | null;
  refresh: () => void;
}

const AiProviderStatusContext = createContext<AiProviderStatusValue | null>(null);

export function AiProviderStatusProvider({ children }: { children: React.ReactNode }) {
  const [hasActiveProvider, setHasActiveProvider] = useState<boolean | null>(null);

  const refresh = useCallback(() => {
    api.workspace
      .listAiProviders()
      .then((configs) => setHasActiveProvider(configs.some((c) => c.is_active)))
      .catch(() => setHasActiveProvider(null));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <AiProviderStatusContext.Provider value={{ hasActiveProvider, refresh }}>
      {children}
    </AiProviderStatusContext.Provider>
  );
}

export function useAiProviderStatus(): AiProviderStatusValue {
  const ctx = useContext(AiProviderStatusContext);
  if (!ctx) throw new Error("useAiProviderStatus must be used within an AiProviderStatusProvider");
  return ctx;
}
