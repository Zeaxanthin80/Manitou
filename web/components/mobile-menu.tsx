"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { DropdownMenu } from "@/components/ui/dropdown-menu";
import { CloseIcon, MenuIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";

export type NavItem = { href: string; label: string };

/**
 * Hamburger menu for a set of navigation links.
 *
 * Used by both headers: the storefront passes categories, the portal passes its
 * sections. It sits to the LEFT of the wordmark, where a phone user's thumb and
 * every other storefront put it.
 *
 * The panel is a dropdown rather than a full-screen overlay -- with a handful of
 * links an overlay would cover the page to show three lines of text. If a store
 * ever has more links than fit a screen this should become a <dialog> so focus
 * is trapped; at this size trapping focus is more disorienting than helpful.
 *
 * `exact` matters for a link like /admin, which is a prefix of every other admin
 * route and would otherwise always look active.
 */
export function MobileMenu({
  items,
  label,
  panelId = "mobile-menu",
  className,
}: {
  items: NavItem[];
  label: string;
  panelId?: string;
  className?: string;
}) {
  const pathname = usePathname();

  return (
    <div className={className}>
      <DropdownMenu
        panelId={panelId}
        align="left"
        panelLabel={label}
        panelClassName="w-56"
        triggerLabel={(open) => (open ? "Close menu" : "Open menu")}
        triggerClassName="-ml-2 flex size-9 items-center justify-center rounded-md text-text transition-colors hover:bg-background motion-reduce:transition-none"
        trigger={(open) =>
          open ? <CloseIcon className="size-6" /> : <MenuIcon className="size-6" />
        }
      >
        <nav aria-label={label}>
          <ul>
            {items.map((item) => {
              const active =
                item.href === "/" || item.href === "/admin"
                  ? pathname === item.href
                  : pathname.startsWith(item.href);
              return (
                <li key={item.href} className="border-b border-border last:border-b-0">
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "block px-4 py-3 font-body text-sm hover:bg-background",
                      active ? "text-accent" : "text-text",
                    )}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </DropdownMenu>
    </div>
  );
}
