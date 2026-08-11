"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { logoutAction } from "@/app/actions/auth";
import { cn } from "@/lib/cn";
import { storeConfig } from "@/lib/store-config";

const LINKS = [
  { href: "/admin", label: "Summary" },
  { href: "/admin/orders", label: "Orders" },
  { href: "/admin/products", label: "Products" },
  { href: "/admin/inventory", label: "Inventory" },
];

/**
 * Vendor portal nav.
 *
 * Same tokens and same type as the storefront -- Section 4.3 asks for the two to
 * be recognisably one product -- with a badge so it is never ambiguous which
 * side you are on. The badge is the accent's job: "you are editing the live
 * store" is exactly the kind of consequential state the Studio direction
 * reserves it for.
 *
 * Client component only to read the current path for the active link, matching
 * CategoryNav. The layout above it stays a Server Component and does the auth
 * check.
 */
export function AdminNav({ email }: { email: string }) {
  const pathname = usePathname();

  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-6 py-4">
        <Link
          href="/admin"
          className="font-display text-lg uppercase tracking-tight text-text"
        >
          {storeConfig.store.name}
        </Link>
        <span className="rounded-sm border border-accent px-2 py-1 font-body text-xs uppercase tracking-tight text-accent">
          Vendor portal
        </span>

        <nav aria-label="Admin" className="flex flex-wrap items-center gap-6">
          {LINKS.map((l) => {
            // startsWith would light up Summary on every page, since every admin
            // path begins with /admin. Only the nested routes match by prefix.
            const active =
              l.href === "/admin"
                ? pathname === "/admin"
                : pathname.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "font-body text-sm transition-colors motion-reduce:transition-none",
                  active
                    ? "text-accent underline decoration-2 underline-offset-8"
                    : "text-muted hover:text-text",
                )}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-4 font-body text-sm">
          <Link href="/" className="text-muted hover:text-text">
            View store
          </Link>
          <span className="hidden text-muted md:inline">{email}</span>
          <form action={logoutAction}>
            <button type="submit" className="text-muted hover:text-text">
              Sign out
            </button>
          </form>
        </div>
      </div>
    </header>
  );
}
