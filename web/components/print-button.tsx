"use client";

import { Button } from "@/components/ui/button";

/**
 * Prints the page it sits on.
 *
 * A client component only because `window.print()` needs one -- `Button` itself
 * is deliberately server-safe, and a consumer attaching onClick is what makes
 * the boundary. This is the smallest possible piece to put on that side.
 *
 * **It hides itself when printing.** A button rendered onto the paper is the
 * classic print-stylesheet miss, and it looks like a bug in the document rather
 * than in the stylesheet.
 *
 * Ctrl+P does the same thing, so this is discoverability rather than capability:
 * a vendor packing an order should not have to know the page is printable.
 */
export function PrintButton({ label }: { label: string }) {
  return (
    <Button variant="ghost" size="sm" className="print:hidden" onClick={() => window.print()}>
      {label}
    </Button>
  );
}
