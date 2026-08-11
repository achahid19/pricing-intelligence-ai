"use client";

// The spotlight itself — a dimmed backdrop with a cutout around the
// current step's Sidebar target (the standard `box-shadow: 0 0 0 9999px`
// technique, no SVG masking needed) plus a floating card with the copy
// and Back/Next/Skip. Everything but the card itself is pointer-events-
// none: clicking through the dimmed area (including the spotlighted
// target) still works — clicking straight to the thing you were just
// told about is a feature, not a bug, and it means the tour never
// actually blocks real use of the app underneath it.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowLeft, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useProductTour } from "@/lib/productTour";

const SPOTLIGHT_PADDING = 8;
const CARD_GAP = 16;
const VIEWPORT_MARGIN = 16;

export function ProductTourOverlay() {
  const { active, step, stepIndex, totalSteps, next, back, skip } = useProductTour();
  const [rect, setRect] = useState<DOMRect | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const [cardPos, setCardPos] = useState<{ top: number; left: number } | null>(null);

  // Re-measure the target on every step change and on resize/scroll — two
  // rAFs on step change gives Sidebar's own effect (auto-opening the
  // mobile drawer for a target that lives inside it, see Sidebar.tsx) a
  // real paint before this measures, not just a microtask.
  useEffect(() => {
    if (!active) return;
    if (!step.target) {
      setRect(null);
      return;
    }
    function measure() {
      const el = document.querySelector(`[data-tour="${step.target}"]`);
      setRect(el ? el.getBoundingClientRect() : null);
    }
    let raf2 = 0;
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(measure);
    });
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      cancelAnimationFrame(raf1);
      cancelAnimationFrame(raf2);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [active, step.target]);

  // Second pass: once the card itself has a real size, place it next to
  // the target (right side, vertically centered) and clamp to the
  // viewport so it never renders partly off-screen on a narrow window.
  useLayoutEffect(() => {
    if (!active) return;
    if (!rect) {
      setCardPos(null); // centered mode, see render below
      return;
    }
    const card = cardRef.current;
    const cardWidth = card?.offsetWidth ?? 320;
    const cardHeight = card?.offsetHeight ?? 160;

    let left = rect.right + CARD_GAP;
    let top = rect.top + rect.height / 2 - cardHeight / 2;

    if (left + cardWidth + VIEWPORT_MARGIN > window.innerWidth) {
      // No room to the right (narrow viewport, e.g. inside the mobile
      // drawer) — place it below the target instead.
      left = Math.max(VIEWPORT_MARGIN, Math.min(rect.left, window.innerWidth - cardWidth - VIEWPORT_MARGIN));
      top = rect.bottom + CARD_GAP;
    }
    top = Math.max(VIEWPORT_MARGIN, Math.min(top, window.innerHeight - cardHeight - VIEWPORT_MARGIN));
    left = Math.max(VIEWPORT_MARGIN, left);

    setCardPos({ top, left });
  }, [active, rect]);

  if (!active) return null;

  const isFirst = stepIndex === 0;
  const isLast = stepIndex === totalSteps - 1;
  const centered = !step.target;

  return (
    <div className="pointer-events-none fixed inset-0 z-[100]">
      {rect ? (
        <div
          className="pointer-events-none fixed rounded-lg transition-all duration-300 ease-out"
          style={{
            top: rect.top - SPOTLIGHT_PADDING,
            left: rect.left - SPOTLIGHT_PADDING,
            width: rect.width + SPOTLIGHT_PADDING * 2,
            height: rect.height + SPOTLIGHT_PADDING * 2,
            boxShadow: "0 0 0 9999px rgba(0,0,0,0.6)",
          }}
        />
      ) : (
        <div className="pointer-events-none fixed inset-0 bg-black/60 transition-opacity duration-300" />
      )}

      <div
        ref={cardRef}
        className={
          centered
            ? "pointer-events-auto fixed top-1/2 left-1/2 w-80 max-w-[90vw] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-paper-raised p-5 shadow-2xl transition-all duration-300"
            : "pointer-events-auto fixed w-80 max-w-[90vw] rounded-xl border border-border bg-paper-raised p-5 shadow-2xl transition-all duration-300"
        }
        style={centered ? undefined : { top: cardPos?.top ?? -9999, left: cardPos?.left ?? -9999 }}
      >
        <div className="flex items-start justify-between gap-3">
          <p className="text-xs font-medium tracking-wide text-slate-soft uppercase">
            Step {stepIndex + 1} of {totalSteps}
          </p>
          <button
            type="button"
            onClick={skip}
            aria-label="Skip tour"
            className="shrink-0 rounded p-0.5 text-slate-soft transition-colors hover:text-ink"
          >
            <X className="size-4" />
          </button>
        </div>
        <h2 className="mt-2 font-[family-name:var(--font-display)] text-lg font-semibold text-ink">{step.title}</h2>
        <p className="mt-1.5 text-sm text-slate">{step.body}</p>
        <div className="mt-4 flex items-center justify-between gap-3">
          {!isFirst ? (
            <Button variant="ghost" size="sm" onClick={back}>
              <ArrowLeft className="size-3.5" />
              Back
            </Button>
          ) : (
            <button type="button" onClick={skip} className="text-sm text-slate-soft transition-colors hover:text-ink">
              Skip
            </button>
          )}
          <Button size="sm" onClick={next}>
            {isLast ? "Get started" : "Next"}
          </Button>
        </div>
      </div>
    </div>
  );
}
