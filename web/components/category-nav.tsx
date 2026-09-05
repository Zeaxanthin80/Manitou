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
                // Every link carries the underline; only its colour changes.
                // Transparent at rest, muted on hover, accent when active --
                // one gesture for "you could be here" and "you are here", and
                // nothing moves when the line appears.
                //
                // decoration-1, not decoration-2. Measured on the render: Inter
                // at 14px has a 1px median stem, so a 2px rule was twice the
                // weight of the letterforms above it and read as a bar. An
                // underline should match the stroke it belongs to. The series
                // strip keeps 2px because its names are set in Archivo Black,
                // whose stems really are that heavy.
                //
                // offset-8 stays: 8px is on the spacing scale (4px x 2) and it
                // clears the descenders of a name like "Jewellery" that a
                // cloned store might have. It is also why the header's nav
                // wrapper needs its py-2 -- see site-header.tsx.
                "underline decoration-1 underline-offset-8 transition-[color,text-decoration-color]",
                active
                  ? "text-accent decoration-accent"
                  : "text-muted decoration-transparent hover:text-text hover:decoration-muted",
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
