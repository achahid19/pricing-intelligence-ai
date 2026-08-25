"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, Send, Trash2 } from "lucide-react";

import { ToolProposalCard } from "@/components/assistant/ToolProposalCard";
import { ACTION_SUGGESTIONS, INFO_SUGGESTIONS, STARTER_SUGGESTIONS, SuggestionChip } from "@/components/assistant/suggestions";
import { AiProviderRequiredNotice } from "@/components/ui/ai-provider-notice";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Textarea } from "@/components/ui/textarea";
import { useAiProviderStatus } from "@/lib/aiProvider";
import { useAssistantChat } from "@/lib/assistantChat";

// The wider, focused view of the exact same conversation the floating
// AssistantWidget shows everywhere else — both read/write the shared
// AssistantChatProvider context (see lib/assistantChat.tsx), so switching
// between this page and the popup never shows a different conversation.
export default function AssistantPage() {
  const { hasActiveProvider } = useAiProviderStatus();
  const { log, sending, updatingCallId, turnCount, sendText, resolveProposal, clearConversation } = useAssistantChat();
  const [input, setInput] = useState("");
  const [confirmingClear, setConfirmingClear] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [log, sending]);

  async function handleSend(e?: React.FormEvent) {
    e?.preventDefault();
    const text = input.trim();
    if (!text) return;
    setInput("");
    await sendText(text);
  }

  const composerDisabled = sending || hasActiveProvider !== true;
  const hasPendingProposal = log.some((item) => item.kind === "proposal" && item.status === "proposed");
  const showFollowUpSuggestions = hasActiveProvider === true && log.length > 0 && !sending && !hasPendingProposal;
  const followUpInfo = INFO_SUGGESTIONS[turnCount % INFO_SUGGESTIONS.length];
  const followUpAction = ACTION_SUGGESTIONS[turnCount % ACTION_SUGGESTIONS.length];

  return (
    <div className="flex h-[calc(100vh-9rem)] flex-col gap-4 md:h-[calc(100vh-6rem)]">
      <PageHeader
        title="Apex"
        description="Ask about your workspace, or ask it to take an action — every write action needs your approval first."
        actions={
          log.length > 0 &&
          (confirmingClear ? (
            <div className="flex items-center gap-1.5">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  clearConversation();
                  setConfirmingClear(false);
                }}
                className="border-danger/30 text-danger hover:bg-danger/10"
              >
                Clear chat
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => setConfirmingClear(false)}>
                Cancel
              </Button>
            </div>
          ) : (
            <Button type="button" variant="outline" size="sm" onClick={() => setConfirmingClear(true)}>
              <Trash2 className="size-3.5" />
              Clear conversation
            </Button>
          ))
        }
      />

      {hasActiveProvider === false && <AiProviderRequiredNotice action="Apex" />}

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto rounded-lg border border-border bg-paper p-4">
        {log.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center text-sm text-slate-soft">
            <Bot className="size-8" />
            <p>Ask about your catalog, competitors, or reports — or ask it to take an action.</p>
            {hasActiveProvider === true && (
              <div className="flex max-w-md flex-wrap justify-center gap-2">
                {STARTER_SUGGESTIONS.map((s) => (
                  <SuggestionChip key={s.text} type={s.type} text={s.text} onClick={() => sendText(s.text)} />
                ))}
              </div>
            )}
          </div>
        )}
        {log.map((item, i) => {
          if (item.kind === "user") {
            return (
              <div key={i} className="flex justify-end">
                <div className="max-w-md rounded-lg bg-accent px-3 py-2 text-sm text-white">{item.text}</div>
              </div>
            );
          }
          if (item.kind === "assistant") {
            return (
              <div key={i} className="flex justify-start">
                <div className="max-w-md whitespace-pre-wrap rounded-lg bg-paper-raised px-3 py-2 text-sm text-ink">
                  {item.text}
                </div>
              </div>
            );
          }
          if (item.kind === "error") {
            return (
              <div key={i} className="flex justify-start">
                <div className="max-w-md rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
                  {item.text}
                </div>
              </div>
            );
          }
          return (
            <div key={i} className="flex justify-start">
              <ToolProposalCard
                toolName={item.toolName}
                display={item.display}
                tier={item.tier}
                status={item.status}
                updating={updatingCallId === item.callId}
                resultSummary={item.resultSummary}
                errorMessage={item.errorMessage}
                onApprove={() => resolveProposal(item.callId, "approve")}
                onDismiss={() => resolveProposal(item.callId, "dismiss")}
              />
            </div>
          );
        })}
        {sending && (
          <div className="flex justify-start">
            <div className="max-w-md rounded-lg bg-paper-raised px-3 py-2 text-sm text-slate-soft">Thinking…</div>
          </div>
        )}
        {showFollowUpSuggestions && (
          <div className="flex flex-wrap justify-start gap-2">
            <SuggestionChip type="info" text={followUpInfo} onClick={() => sendText(followUpInfo)} />
            <SuggestionChip type="action" text={followUpAction} onClick={() => sendText(followUpAction)} />
          </div>
        )}
      </div>

      <form onSubmit={handleSend} className="flex gap-2">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={hasActiveProvider === false ? "Set up an AI provider in Settings first" : "Ask Apex…"}
          disabled={composerDisabled}
          rows={2}
          className="resize-none"
        />
        <Button type="submit" disabled={composerDisabled || !input.trim()} aria-label="Send">
          <Send className="size-4" />
        </Button>
      </form>
    </div>
  );
}
