"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/cn";

/**
 * Built on the native <dialog> element rather than a div with a backdrop.
 *
 * showModal() gives four things that are genuinely hard to hand-build and are
 * where accessible modals usually go wrong:
 *
 *   1. Focus is trapped inside -- Tab cannot escape to the page behind.
 *   2. Escape closes it, with no key handler of our own.
 *   3. Everything behind becomes inert to clicks and to assistive tech.
 *   4. It renders in the browser's top layer, so no z-index fight is possible.
 *
 * Focus also returns to whatever opened it on close, which is the behaviour
 * people most often forget when rolling their own.
 *
 * 'use client' is required: useRef, useEffect, and showModal() are all browser
 * concerns.
 */

export type ModalProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  className?: string;
};

export function Modal({ open, onClose, title, children, className }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    // showModal() is what activates the top layer, focus trap and inerting.
    // Calling .show() instead would silently give up all four.
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby="modal-title"
      // Fires for Escape as well as close(), so the parent's state stays in
      // sync however the dialog was dismissed.
      onClose={onClose}
      onClick={(event) => {
        // A click landing on the dialog itself is the backdrop; anything inside
        // hits a child first and stops here.
        if (event.target === ref.current) onClose();
      }}
      className={cn(
        "m-auto w-full max-w-lg rounded-lg border border-border bg-surface p-0 text-text shadow-lg",
        "backdrop:bg-text/40",
        className,
      )}
    >
      <div className="border-b border-border px-4 py-3">
        <h2 id="modal-title" className="font-display text-lg text-text">
          {title}
        </h2>
      </div>
      <div className="p-4 font-body text-base">{children}</div>
    </dialog>
  );
}
