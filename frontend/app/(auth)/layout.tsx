import { ThemeToggle } from "@/components/ThemeToggle";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="hidden flex-col justify-between bg-panel p-12 text-white lg:flex">
        <span className="font-[family-name:var(--font-display)] text-lg font-semibold">
          Pricing Intelligence AI
        </span>
        <div className="max-w-sm">
          <p className="font-[family-name:var(--font-display)] text-3xl leading-tight font-semibold text-balance">
            Know your competitors before they know you.
          </p>
          <p className="mt-4 text-sm text-white/60">
            AI finds and tracks the market around your catalog — bring your own AI provider key, we handle the rest.
          </p>
        </div>
        <p className="text-xs text-white/40">© 2026 Pricing Intelligence AI</p>
      </div>
      <div className="relative flex items-center justify-center p-8">
        <ThemeToggle className="absolute top-6 right-6 inline-flex size-9 items-center justify-center rounded-md text-slate transition-colors hover:bg-black/[0.04] hover:text-ink" />
        <div className="w-full max-w-sm">{children}</div>
      </div>
    </div>
  );
}
