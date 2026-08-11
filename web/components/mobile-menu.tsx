"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { CloseIcon, MenuIcon } from "@/components/ui/icons";
import { useDismissable } from "@/components/ui/use-dismissable";
import { cn } from "@/lib/cn";
import type { Category } from "@/lib/api";

/**
 * Hamburger menu for the category links, shown at 768px and below.
 *
 * It sits to the LEFT of the wordmark, which is where a phone user's thumb and
 * every other storefront put it.
 *
 * The panel is a real dropdown rather than a full-screen overlay: with three
 * categories an overlay would cover the page to show two lines of text. If the
 * category list grows past a screenful, this should become a <dialog> so focus
 * is trapped -- at this size, trapping focus would be more disorienting than
 * helpful.
 */
export function MobileMenu({ categories }: { categories: Category[] }) {
  const { open, setOpen, ref } = useDismissable<HTMLDivElement>();
  const pathname = usePathname();

  return (
    <div ref={ref} className="relative wide:hidden">
      <button
        type="button"
        data-menu-trigger
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls="mobile-menu"
        aria-label={open ? "Close menu" : "Open menu"}
        className="-ml-2 flex size-9 items-center justify-center rounded-md text-text transition-colors hover:bg-background motion-reduce:transition-none"
      >
        {open ? <CloseIcon className="size-6" /> : <MenuIcon className="size-6" />}
      </button>

      {open && (
        <nav
          id="mobile-menu"
          aria-label="Categories"
          className="absolute left-0 z-50 mt-2 w-56 overflow-hidden rounded-md border border-border bg-surface shadow-md"
        >
          <ul>
            {categories.map((c) => {
              const active = pathname === `/categories/${c.slug}`;
              return (
                <li key={c.id} className="border-b border-border last:border-b-0">
                  <Link
                    href={`/categories/${c.slug}`}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "block px-4 py-3 font-body text-sm hover:bg-background",
                      active ? "text-accent" : "text-text",
                    )}
                  >
                    {c.name}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      )}
    </div>
  );
}
