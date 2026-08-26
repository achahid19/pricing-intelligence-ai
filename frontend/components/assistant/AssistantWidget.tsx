"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { Bot, Send, Trash2, X } from "lucide-react";

import { ToolProposalCard } from "@/components/assistant/ToolProposalCard";
import { ACTION_SUGGESTIONS, INFO_SUGGESTIONS, STARTER_SUGGESTIONS, SuggestionChip } from "@/components/assistant/suggestions";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAiProviderStatus } from "@/lib/aiProvider";
import { useAssistantChat } from "@/lib/assistantChat";

export function AssistantWidget() {
  const pathname = usePathname();
  const { hasActiveProvider } = useAiProviderStatus();
  const { log, sending, updatingCallId, turnCount, sendText, resolveProposal, clearConversation } = useAssistantChat();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [confirmingClear, setConfirmingClear] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [log, sending, open]);

  useEffect(() => {
    setConfirmingClear(false);
  }, [open]);

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

  // The full /assistant page already shows this same conversation at full
  // width — the floating popup would just be a redundant duplicate on top
  // of it, so it stays out of the way there entirely (both the button and
  // the panel), same idea as not stacking two chat windows on the screen.
  if (pathname === "/assistant") return null;

  return (
    <>
      {open && (
        <div className="fixed bottom-24 right-4 z-40 flex h-[70vh] max-h-[600px] w-[calc(100vw-2rem)] max-w-sm flex-col overflow-hidden rounded-xl border border-border bg-paper shadow-2xl sm:w-96">
          <div className="flex items-center justify-between border-b border-border bg-paper-raised px-4 py-3">
            <div className="flex items-center gap-2">
              <Bot className="size-4 text-accent" />
              <p className="font-[family-name:var(--font-display)] text-sm font-semibold text-ink">Apex</p>
            </div>
            <div className="flex items-center gap-1">
              {!confirmingClear && log.length > 0 && (
                <button
                  type="button"
                  onClick={() => setConfirmingClear(true)}
                  aria-label="Clear conversation"
                  className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-danger/10 hover:text-danger"
                >
                  <Trash2 className="size-4" />
                </button>
              )}
              {confirmingClear && (
                <>
                  <button
                    type="button"
                    onClick={() => {
                      clearConversation();
                      setConfirmingClear(false);
                    }}
                    className="rounded-md px-2 py-1 text-xs font-medium text-danger transition-colors hover:bg-danger/10"
                  >
                    Clear chat
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmingClear(false)}
                    aria-label="Cancel"
                    className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-black/[0.03] hover:text-ink"
                  >
                    <X className="size-3.5" />
                  </button>
                </>
              )}
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close Apex"
                className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-black/[0.03] hover:text-ink"
              >
                <X className="size-4" />
              </button>
            </div>
          </div>

          {hasActiveProvider === false && (
            <div className="border-b border-border bg-accent/5 px-4 py-2 text-xs text-ink">
              Set up an AI provider in{" "}
              <a href="/settings" className="font-medium text-accent hover:underline">
                Settings
              </a>{" "}
              to use Apex.
            </div>
          )}

          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
            {log.length === 0 && (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-sm text-slate-soft">
                <Bot className="size-7" />
                <p>Ask about your catalog, competitors, or reports, or ask it to take an action.</p>
                {hasActiveProvider === true && (
                  <div className="flex flex-wrap justify-center gap-2">
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
                    <div className="max-w-[85%] rounded-lg bg-accent px-3 py-2 text-sm text-white">{item.text}</div>
                  </div>
                );
              }
              if (item.kind === "assistant") {
                return (
                  <div key={i} className="flex justify-start">
                    <div className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-paper-raised px-3 py-2 text-sm text-ink">
                      {item.text}
                    </div>
                  </div>
                );
              }
              if (item.kind === "error") {
                return (
                  <div key={i} className="flex justify-start">
                    <div className="max-w-[85%] rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
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
                <div className="max-w-[85%] rounded-lg bg-paper-raised px-3 py-2 text-sm text-slate-soft">Thinking…</div>
              </div>
            )}
            {showFollowUpSuggestions && (
              <div className="flex flex-wrap justify-start gap-2">
                <SuggestionChip type="info" text={followUpInfo} onClick={() => sendText(followUpInfo)} />
                <SuggestionChip type="action" text={followUpAction} onClick={() => sendText(followUpAction)} />
              </div>
            )}
          </div>

          <form onSubmit={handleSend} className="flex gap-2 border-t border-border p-3">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder={hasActiveProvider === false ? "Set up an AI provider first" : "Ask Apex…"}
              disabled={composerDisabled}
              rows={1}
              className="max-h-24 min-h-10 resize-none py-2"
            />
            <Button type="submit" disabled={composerDisabled || !input.trim()} aria-label="Send" className="shrink-0">
              <Send className="size-4" />
            </Button>
          </form>
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "Close Apex" : "Open Apex"}
        className="fixed bottom-4 right-4 z-40 flex size-14 items-center justify-center rounded-full bg-accent text-white shadow-lg transition-transform hover:scale-105 hover:bg-accent-hover"
      >
        {open ? <X className="size-6" /> : <Bot className="size-6" />}
      </button>
    </>
  );
}
