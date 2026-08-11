"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { cn } from "@/lib/cn";

/**
 * Transient messages -- "Added to cart", "Product saved".
 *
 * The live region is the part that matters for accessibility. A toast that only
 * appears visually is invisible to a screen reader user, who then gets no
 * confirmation that anything happened. aria-live="polite" announces it without
 * interrupting whatever is being read; role="status" gives it the right
 * semantics.
 *
 * The region is rendered ALWAYS, empty or not. Assistive tech watches a live
 * region for changes, so one that only appears when there is something to say
 * is frequently missed -- the element has to exist first.
 */

type Tone = "info" | "success" | "error";
type Toast = { id: number; message: string; tone: Tone };

const ToastContext = createContext<{
  toast: (message: string, tone?: Tone) => void;
} | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}

const TONES: Record<Tone, string> = {
  info: "border-border bg-surface text-text",
  success: "border-success bg-surface text-success",
  error: "border-error bg-surface text-error",
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback((message: string, tone: Tone = "info") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, message, tone }]);
    window.setTimeout(
      () => setToasts((current) => current.filter((t) => t.id !== id)),
      4000,
    );
  }, []);

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "pointer-events-auto w-full max-w-sm rounded-md border px-4 py-3 font-body text-sm shadow-md",
              // Keyframe lives in globals.css inside a prefers-reduced-motion
              // query, so it is absent entirely for anyone who opted out.
              "animate-toast",
              TONES[t.tone],
            )}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
