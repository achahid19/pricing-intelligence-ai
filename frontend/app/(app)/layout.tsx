"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AssistantWidget } from "@/components/assistant/AssistantWidget";
import { ProductTourOverlay } from "@/components/ProductTourOverlay";
import { Sidebar } from "@/components/Sidebar";
import { api, clearToken, getToken, type Workspace } from "@/lib/api";
import { ActivityProvider } from "@/lib/activity";
import { AiProviderStatusProvider } from "@/lib/aiProvider";
import { AssistantChatProvider } from "@/lib/assistantChat";
import { PipelineStatusPoller } from "@/lib/pipelineStatus";
import { ProductTourProvider } from "@/lib/productTour";

export default function AppLayout({ children }: { children: React.ReactNode }) {
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

  if (!workspace) return null;

  return (
    <ActivityProvider>
      <PipelineStatusPoller />
      <AiProviderStatusProvider>
        <AssistantChatProvider>
          <ProductTourProvider workspace={workspace}>
            <ProductTourOverlay />
            <div className="flex h-full flex-col md:flex-row">
              <Sidebar workspaceName={workspace.name} />
              <main className="flex-1 overflow-y-auto">{children}</main>
            </div>
            <AssistantWidget />
          </ProductTourProvider>
        </AssistantChatProvider>
      </AiProviderStatusProvider>
    </ActivityProvider>
  );
}
