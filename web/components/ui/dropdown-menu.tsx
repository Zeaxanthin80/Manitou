"use client";

import { useDismissable } from "@/components/ui/use-dismissable";
import { cn } from "@/lib/cn";

/**
 * A trigger button and the panel it opens.
 *
 * Extracted once four of these existed -- the storefront's hamburger and avatar
 * menus, and the portal's. Every one needs the same three exits (Escape, click
 * outside, navigating away) and the same aria-expanded/aria-controls wiring, and
 * four copies of that is four chances for one of them to quietly lose a
 * behaviour.
 *
 * The panel is only mounted while open. That keeps closed menus out of the
 * accessibility tree entirely, rather than relying on `hidden` and hoping.
 */
export function DropdownMenu({
  panelId,
  triggerLabel,
  triggerClassName,
  trigger,
  align = "left",
  panelClassName,
  panelRole,
  panelLabel,
  children,
}: {
  panelId: string;
  /** The accessible name of the button. The visible content is usually an icon
   *  or initials, neither of which reads as anything useful. */
  triggerLabel: string | ((open: boolean) => string);
  triggerClassName?: string;
  /** Takes `open` so a trigger can swap its icon (hamburger to close). */
  trigger: React.ReactNode | ((open: boolean) => React.ReactNode);
  align?: "left" | "right";
  panelClassName?: string;
  /** "menu" for a list of actions. Omit when the panel holds a <nav>, which
   *  carries its own semantics and must not be nested inside a menu role. */
  panelRole?: "menu";
  panelLabel?: string;
  children: React.ReactNode;
}) {
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        data-menu-trigger
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={panelId}
        // Only when the panel really is a menu. A hamburger opening a <nav> is
        // not a menu in the ARIA sense, and claiming it is would have a screen
        // reader announce menu semantics for a list of links.
        aria-haspopup={panelRole === "menu" ? "menu" : undefined}
        aria-label={
          typeof triggerLabel === "function" ? triggerLabel(open) : triggerLabel
        }
        className={triggerClassName}
      >
        {typeof trigger === "function" ? trigger(open) : trigger}
      </button>

      {open && (
        <div
          id={panelId}
          role={panelRole}
          aria-label={panelLabel}
          className={cn(
            "absolute z-50 mt-2 overflow-hidden rounded-md border border-border bg-surface shadow-md",
            align === "right" ? "right-0" : "left-0",
            panelClassName,
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}

/** Shared row styling so every menu item looks identical wherever it appears. */
export const menuItemClass =
  "block w-full px-4 py-2 text-left font-body text-sm text-text hover:bg-background";
