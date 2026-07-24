"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { api, clearToken, getToken, type Workspace } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api.workspace
      .me()
      .then((ws) => {
        if (!ws.onboarding_completed) router.replace("/onboarding");
        else setWorkspace(ws);
      })
      .catch(() => {
        clearToken();
        router.replace("/login");
      });
  }, [router]);

  function handleLogout() {
    clearToken();
    router.replace("/login");
  }

  if (!workspace) return null;

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <div className="text-center">
        <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-ink">
          Welcome, {workspace.name}
        </h1>
        <p className="mt-2 text-sm text-slate">
          Onboarding complete — catalog and discovery come next.
        </p>
        <Button variant="outline" className="mt-6" onClick={handleLogout}>
          Log out
        </Button>
      </div>
    </main>
  );
}
