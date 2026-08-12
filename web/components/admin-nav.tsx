"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { logoutAction } from "@/app/actions/auth";
import { MobileMenu } from "@/components/mobile-menu";
import type { NavItem } from "@/components/mobile-menu";
import { avatarClass, initials } from "@/components/ui/avatar";
import { DropdownMenu, menuItemClass } from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/cn";
import { storeConfig } from "@/lib/store-config";

const SECTIONS: NavItem[] = [
  { href: "/admin", label: "Summary" },
  { href: "/admin/orders", label: "Orders" },
  { href: "/admin/products", label: "Products" },
  { href: "/admin/inventory", label: "Inventory" },
];

/**
 * Vendor portal nav.
 *
 * Same tokens, same type and the same two menu components as the storefront --
 * Section 4.3 asks for the two halves to be recognisably one product, and the
 * surest way to keep that true is to share the components rather than match them
 * by eye. The accent badge is the only thing that says which side you are on:
 * "you are editing the live store" is exactly the consequential state the Studio
 * direction reserves the accent for.
 *
 * Collapses below `lg` (1024px), not at the storefront's 769px. That is measured
 * rather than assumed: this bar carries four sections plus View store, an email
 * and Sign out, and it does not fit on one line until 1024px. Using the
 * storefront's breakpoint would have left a three-row stack between 769 and 1023.
 */
export function AdminNav({
  email,
  fullName,
}: {
  email: string;
  fullName: string;
}) {
  const pathname = usePathname();

  return (
    <header className="border-b border-border bg-surface">
      <nav
        aria-label="Admin"
        className="mx-auto flex max-w-6xl items-center gap-3 px-6 py-4 lg:gap-6"
      >
        <MobileMenu
          items={SECTIONS}
          label="Portal sections"
          panelId="admin-menu"
          className="lg:hidden"
        />

        <Link
          href="/admin"
          className="shrink-0 font-display text-lg uppercase tracking-tight text-text"
        >
          {storeConfig.store.name}
        </Link>

        {/* The badge is the one thing that must never be dropped on a small
            screen -- it is what distinguishes the portal from the storefront. */}
        <span className="shrink-0 rounded-sm border border-accent px-2 py-1 font-body text-xs uppercase tracking-tight text-accent">
          <span className="hidden sm:inline">Vendor portal</span>
          <span className="sm:hidden">Admin</span>
        </span>

        <div className="hidden items-center gap-6 lg:flex">
          {SECTIONS.map((s) => {
            // Every admin path starts with /admin, so Summary has to match
            // exactly or it lights up on every page.
            const active =
              s.href === "/admin"
                ? pathname === "/admin"
                : pathname.startsWith(s.href);
            return (
              <Link
                key={s.href}
                href={s.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "font-body text-sm transition-colors motion-reduce:transition-none",
                  active
                    ? "text-accent underline decoration-2 underline-offset-8"
                    : "text-muted hover:text-text",
                )}
              >
                {s.label}
              </Link>
            );
          })}
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-4">
          <Link
            href="/"
            className="hidden font-body text-sm text-muted hover:text-text lg:inline"
          >
            View store
          </Link>

          <DropdownMenu
            panelId="admin-account-menu"
            align="right"
            panelRole="menu"
            panelClassName="w-56"
            triggerLabel={`Account menu for ${fullName || email}`}
            triggerClassName={avatarClass}
            trigger={initials(fullName, email)}
          >
            <div className="border-b border-border px-4 py-3">
              <p className="font-body text-sm text-text">{fullName}</p>
              <p className="truncate font-body text-xs text-muted" title={email}>
                {email}
              </p>
            </div>

            {/* Duplicated from the bar on purpose: on a phone the bar's copy is
                hidden, and leaving the store unreachable from the portal would
                strand the vendor. */}
            <Link href="/" role="menuitem" className={menuItemClass}>
              View store
            </Link>
            <Link href="/account" role="menuitem" className={menuItemClass}>
              Your account
            </Link>

            <div className="border-t border-border">
              <form action={logoutAction}>
                <button type="submit" role="menuitem" className={menuItemClass}>
                  Sign out
                </button>
              </form>
            </div>
          </DropdownMenu>
        </div>
      </nav>
    </header>
  );
}
