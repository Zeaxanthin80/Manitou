"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

/**
 * Open/closed state for a popover-style menu, with the three ways users expect
 * to get out of one:
 *
 *   Escape            -- the keyboard exit. Without it a keyboard user who opens
 *                        the menu by accident has no way back except tabbing
 *                        through every item.
 *   click outside     -- the pointer exit.
 *   navigating away   -- the one that is easy to miss. These menus contain
 *                        links; in the App Router a <Link> changes the URL
 *                        without unmounting the header, so the panel would stay
 *                        open over the page it just navigated to.
 *
 * Returns a ref to put on the wrapper element -- "outside" is defined as
 * anything that element does not contain, so the trigger and the panel must both
 * live inside it.
 */
export function useDismissable<T extends HTMLElement>() {
  const [open, setOpen] = useState(false);
  const ref = useRef<T>(null);
  const pathname = usePathname();

  // Close on navigation. Depending on pathname rather than listening to clicks
  // means it also covers back/forward and programmatic navigation.
  //
  // Adjusted DURING RENDER rather than in an effect. React documents this as the
  // way to reset state when a value changes, and it is better here in two ways:
  // React re-runs this component immediately without painting the intermediate
  // state, so the menu never flashes open on the new page -- which an effect
  // allows, since effects run after paint. It also drops a render pass.
  const [lastPath, setLastPath] = useState(pathname);
  if (lastPath !== pathname) {
    setLastPath(pathname);
    setOpen(false);
  }

  useEffect(() => {
    if (!open) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        // Return focus to the trigger; otherwise Escape leaves focus on a
        // element that is no longer rendered and the tab order restarts.
        ref.current?.querySelector<HTMLElement>("[data-menu-trigger]")?.focus();
      }
    };

    const onPointerDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };

    document.addEventListener("keydown", onKeyDown);
    // pointerdown, not click: a click fires after mouseup, so a drag that starts
    // inside the panel and ends outside would close it unexpectedly.
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [open]);

  return { open, setOpen, ref };
}
