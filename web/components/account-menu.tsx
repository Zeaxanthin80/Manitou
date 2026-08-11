"use client";

import Link from "next/link";

import { logoutAction } from "@/app/actions/auth";
import { useDismissable } from "@/components/ui/use-dismissable";
import type { User } from "@/lib/api";

/**
 * Avatar button with an account dropdown.
 *
 * The avatar replaces the email address that used to sit in the nav. Two
 * reasons: a long address was most of a phone's width, and an email on screen is
 * a small privacy leak in any shared or shoulder-surfed context. The full
 * address is still one click away, at the top of the menu.
 *
 * Initials, not a photo -- there is no avatar upload in the schema, and inventing
 * one would be a Phase 4 feature pulled forward. This renders what we actually
 * have.
 */
function initials(user: User) {
  const parts = user.full_name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  // Someone with a blank name still needs a marker; the email always exists.
  return user.email.slice(0, 2).toUpperCase();
}

export function AccountMenu({ user }: { user: User }) {
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();

  const item =
    "block w-full px-4 py-2 text-left font-body text-sm text-text hover:bg-background";

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        data-menu-trigger
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls="account-menu"
        // The accessible name has to say who this is -- "CC" read aloud is
        // meaningless, and the visible initials are decorative.
        aria-label={`Account menu for ${user.full_name || user.email}`}
        className="flex size-9 items-center justify-center rounded-full bg-primary font-body text-xs text-surface transition-colors hover:bg-text motion-reduce:transition-none"
      >
        {initials(user)}
      </button>

      {open && (
        <div
          id="account-menu"
          role="menu"
          className="absolute right-0 z-50 mt-2 w-56 overflow-hidden rounded-md border border-border bg-surface shadow-md"
        >
          <div className="border-b border-border px-4 py-3">
            <p className="font-body text-sm text-text">{user.full_name}</p>
            {/* truncate + title: a long address shortens visibly instead of
                stretching the panel, and hovering still reveals all of it. */}
            <p className="truncate font-body text-xs text-muted" title={user.email}>
              {user.email}
            </p>
          </div>

          <Link href="/account" role="menuitem" className={item}>
            Your account
          </Link>
          <Link href="/orders" role="menuitem" className={item}>
            Your orders
          </Link>

          <div className="border-t border-border">
            {/* Still a form, not a link: signing out changes state, and a GET
                that mutates can be fired by a prefetch or a crawler. */}
            <form action={logoutAction}>
              <button type="submit" role="menuitem" className={item}>
                Sign out
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
