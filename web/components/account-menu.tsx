"use client";

import Link from "next/link";

import { logoutAction } from "@/app/actions/auth";
import { avatarClass, initial } from "@/components/ui/avatar";
import { DropdownMenu, menuItemClass } from "@/components/ui/dropdown-menu";
import type { User } from "@/lib/api";

/**
 * Avatar button with an account dropdown.
 *
 * The avatar replaces the email address that used to sit in the nav: a long
 * address was most of a phone's width, and an email on screen is a small privacy
 * leak in any shared or shoulder-surfed context. The full address is still one
 * click away, at the top of the menu.
 */
export function AccountMenu({ user }: { user: User }) {
  return (
    <DropdownMenu
      panelId="account-menu"
      align="right"
      panelRole="menu"
      panelClassName="w-56"
      // "CC" read aloud means nothing, so the button says who it belongs to.
      triggerLabel={`Account menu for ${user.full_name || user.email}`}
      triggerClassName={avatarClass}
      trigger={initial(user.full_name, user.email)}
    >
      <div className="border-b border-border px-4 py-3">
        <p className="font-body text-sm text-text">{user.full_name}</p>
        {/* truncate + title: a long address shortens visibly instead of
            stretching the panel, and hovering still reveals all of it. */}
        <p className="truncate font-body text-xs text-muted" title={user.email}>
          {user.email}
        </p>
      </div>

      {/* Admins only. Hiding it from customers is cosmetic, not a control: the
          layout gates the route and the API gates the data, independently. */}
      {user.role === "admin" && (
        <Link
          href="/admin"
          role="menuitem"
          className={`${menuItemClass} border-b border-border text-accent`}
        >
          Vendor portal
        </Link>
      )}

      <Link href="/account" role="menuitem" className={menuItemClass}>
        Your account
      </Link>
      <Link href="/orders" role="menuitem" className={menuItemClass}>
        Your orders
      </Link>

      <div className="border-t border-border">
        {/* Still a form, not a link: signing out changes state, and a GET that
            mutates can be fired by a prefetch or a crawler. */}
        <form action={logoutAction}>
          <button type="submit" role="menuitem" className={menuItemClass}>
            Sign out
          </button>
        </form>
      </div>
    </DropdownMenu>
  );
}
