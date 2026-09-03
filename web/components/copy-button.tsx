"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

type State = "idle" | "copied" | "failed";

/**
 * Copies a string to the clipboard and says whether it worked.
 *
 * **It reports failure rather than pretending.** `navigator.clipboard` only
 * exists in a secure context, and even there a browser can refuse — so a button
 * that silently does nothing leaves someone pasting the previous clipboard
 * contents into a carrier's address form without noticing. Saying "Couldn't
 * copy" is worth more than a confident tick.
 *
 * The label change is announced with aria-live, because for a screen reader
 * nothing else about the page changes when this succeeds — the whole feedback
 * is one word swapping in place.
 */
export function CopyButton({
  text,
  label,
  className,
}: {
  text: string;
  label: string;
  className?: string;
}) {
  const [state, setState] = useState<State>("idle");

  // The effect owns the timer, so it is cleared if the component unmounts or the
  // button is pressed again before the two seconds are up.
  useEffect(() => {
    if (state === "idle") return;
    const timer = setTimeout(() => setState("idle"), 2000);
    return () => clearTimeout(timer);
  }, [state]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      // Insecure context, a permissions policy, or a browser that declined.
      setState("failed");
    }
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={copy}
      className={className}
      // The text is what changes, so the button announces its own result.
      aria-live="polite"
    >
      {state === "copied" ? "Copied" : state === "failed" ? "Couldn't copy" : label}
    </Button>
  );
}
