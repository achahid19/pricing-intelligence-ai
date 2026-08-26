"use client";

// The assistant's conversation state, lifted out of any single page and
// mounted once at the (app)/layout.tsx level (same placement as
// ActivityProvider/AiProviderStatusProvider) — this is what lets the
// AssistantWidget survive navigating between pages instead of resetting
// every time, and it's persisted to localStorage on every change so it
// also survives a full page reload. `sending`/`updatingCallId` are
// deliberately NOT persisted — an in-flight request is genuinely gone
// after a reload (the fetch itself doesn't survive), so resuming a
// "Thinking…" bubble forever would be wrong; those always start fresh.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import {
  api,
  ApiError,
  ASSISTANT_CHAT_STORAGE_KEY,
  type AssistantToolCallStatus,
  type ChatMessage,
  type ModelTier,
  type ToolCallDisplay,
} from "@/lib/api";

export type DisplayItem =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string }
  | { kind: "error"; text: string }
  | {
      kind: "proposal";
      callId: number;
      toolName: string;
      display: ToolCallDisplay;
      tier: ModelTier;
      status: AssistantToolCallStatus;
      resultSummary?: Record<string, unknown> | null;
      errorMessage?: string | null;
    };

interface PersistedChat {
  messages: ChatMessage[];
  log: DisplayItem[];
  turnCount: number;
}

const EMPTY_CHAT: PersistedChat = { messages: [], log: [], turnCount: 0 };

function loadPersisted(): PersistedChat {
  if (typeof window === "undefined") return EMPTY_CHAT;
  try {
    const raw = localStorage.getItem(ASSISTANT_CHAT_STORAGE_KEY);
    if (!raw) return EMPTY_CHAT;
    const parsed = JSON.parse(raw);
    return {
      messages: Array.isArray(parsed.messages) ? parsed.messages : [],
      log: Array.isArray(parsed.log) ? parsed.log : [],
      turnCount: typeof parsed.turnCount === "number" ? parsed.turnCount : 0,
    };
  } catch {
    return EMPTY_CHAT;
  }
}

interface AssistantChatValue {
  messages: ChatMessage[];
  log: DisplayItem[];
  sending: boolean;
  updatingCallId: number | null;
  turnCount: number;
  sendText: (text: string) => Promise<void>;
  resolveProposal: (callId: number, action: "approve" | "dismiss") => Promise<void>;
  clearConversation: () => void;
}

const AssistantChatContext = createContext<AssistantChatValue | null>(null);

export function AssistantChatProvider({ children }: { children: React.ReactNode }) {
  // Lazy initializers so a reload picks up whatever was last saved on the
  // very first render, not one render late (which would otherwise flash
  // an empty conversation before snapping to the real one).
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadPersisted().messages);
  const [log, setLog] = useState<DisplayItem[]>(() => loadPersisted().log);
  const [turnCount, setTurnCount] = useState<number>(() => loadPersisted().turnCount);
  const [sending, setSending] = useState(false);
  const [updatingCallId, setUpdatingCallId] = useState<number | null>(null);

  useEffect(() => {
    localStorage.setItem(ASSISTANT_CHAT_STORAGE_KEY, JSON.stringify({ messages, log, turnCount }));
  }, [messages, log, turnCount]);

  const sendText = useCallback(
    async (text: string) => {
      if (!text || sending) return;
      const nextMessages: ChatMessage[] = [...messages, { role: "user", content: text }];
      setMessages(nextMessages);
      setLog((prev) => [...prev, { kind: "user", text }]);
      setSending(true);
      try {
        const res = await api.assistant.sendMessage(nextMessages);
        if (res.type === "message") {
          setMessages((prev) => [...prev, { role: "assistant", content: res.text }]);
          setLog((prev) => [...prev, { kind: "assistant", text: res.text }]);
          setTurnCount((c) => c + 1);
        } else {
          setLog((prev) => [
            ...prev,
            {
              kind: "proposal",
              callId: res.call_id,
              toolName: res.tool_name,
              display: res.display,
              tier: res.tier,
              status: "proposed",
            },
          ]);
        }
      } catch (err) {
        setLog((prev) => [
          ...prev,
          { kind: "error", text: err instanceof ApiError ? err.message : "Something went wrong. Try again." },
        ]);
      } finally {
        setSending(false);
      }
    },
    [messages, sending]
  );

  const resolveProposal = useCallback(async (callId: number, action: "approve" | "dismiss") => {
    setUpdatingCallId(callId);
    try {
      const call =
        action === "approve"
          ? await api.assistant.approveToolCall(callId)
          : await api.assistant.dismissToolCall(callId);
      setLog((prev) =>
        prev.map((item) =>
          item.kind === "proposal" && item.callId === callId
            ? { ...item, status: call.status, resultSummary: call.result_summary, errorMessage: call.error_message }
            : item
        )
      );
      const resolutionNote =
        call.status === "executed"
          ? `Approved and executed. Result: ${JSON.stringify(call.result_summary)}`
          : call.status === "failed"
            ? `Approved, but it failed: ${call.error_message}`
            : "Dismissed by the user, not executed.";
      setMessages((prev) => [...prev, { role: "assistant", content: `(proposed ${call.tool_name}) ${resolutionNote}` }]);
      setTurnCount((c) => c + 1);
    } catch (err) {
      setLog((prev) => [
        ...prev,
        { kind: "error", text: err instanceof ApiError ? err.message : "Something went wrong. Try again." },
      ]);
    } finally {
      setUpdatingCallId(null);
    }
  }, []);

  const clearConversation = useCallback(() => {
    setMessages([]);
    setLog([]);
    setTurnCount(0);
  }, []);

  const value = useMemo(
    () => ({ messages, log, sending, updatingCallId, turnCount, sendText, resolveProposal, clearConversation }),
    [messages, log, sending, updatingCallId, turnCount, sendText, resolveProposal, clearConversation]
  );

  return <AssistantChatContext.Provider value={value}>{children}</AssistantChatContext.Provider>;
}

export function useAssistantChat(): AssistantChatValue {
  const ctx = useContext(AssistantChatContext);
  if (!ctx) throw new Error("useAssistantChat must be used within an AssistantChatProvider");
  return ctx;
}
