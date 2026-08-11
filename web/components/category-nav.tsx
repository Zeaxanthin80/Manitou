"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";
import type { Category } from "@/lib/api";

/**
 * Client component purely so it can read the current path and mark the active
 * category. SiteHeader stays a Server Component and does the fetching, passing
 * the result down -- the client boundary is drawn as tightly as possible around
 * the one thing that actually needs the browser.
 *
 * This is the only place the accent appears in the nav. Studio uses one sharp
 * accent SPARINGLY; marking where you are is a real signal, decoration is not.
 */
export function CategoryNav({ categories }: { categories: Category[] }) {
  const pathname = usePathname();

  return (
    // flex-nowrap, not flex-wrap: the header gives this a scrollable row, and a
    // list that wraps inside a scroll container makes the container taller
    // instead of scrolling. One line that scrolls beats three lines that don't.
    <ul className="flex flex-nowrap items-center gap-6">
      {categories.map((c) => {
        const active = pathname === `/categories/${c.slug}`;
        return (
          <li key={c.id} className="shrink-0">
            <Link
              href={`/categories/${c.slug}`}
              aria-current={active ? "page" : undefined}
              className={cn(
                "block whitespace-nowrap font-body text-sm transition-colors motion-reduce:transition-none",
                active
                  ? "text-accent underline decoration-2 underline-offset-8"
                  : "text-muted hover:text-text",
              )}
            >
              {c.name}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
