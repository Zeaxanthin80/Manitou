import Link from "next/link";

import { cn } from "@/lib/cn";

/**
 * Styled wrappers around real <table> elements -- not a data grid.
 *
 * Phase 4's vendor portal is table-heavy and needs a consistent look, not a
 * framework. Real table semantics also give screen readers row/column context
 * that a grid of <div>s cannot.
 *
 * The outer wrapper scrolls horizontally so a wide table never forces the page
 * itself sideways on a narrow screen -- part of Section 4.3's responsive floor.
 */

export function Table({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <div className="w-full overflow-x-auto">
      <table
        className={cn("w-full border-collapse font-body text-sm", className)}
        {...props}
      />
    </div>
  );
}

export function THead({ className, ...props }: React.ComponentProps<"thead">) {
  return <thead className={cn("border-b border-border", className)} {...props} />;
}

export function TBody(props: React.ComponentProps<"tbody">) {
  return <tbody {...props} />;
}

export function TR({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr className={cn("border-b border-border last:border-0", className)} {...props} />
  );
}

export function TH({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      // scope is what tells a screen reader which cells this header describes.
      scope="col"
      className={cn("px-3 py-2 text-left text-xs text-muted", className)}
      {...props}
    />
  );
}

export function TD({ className, ...props }: React.ComponentProps<"td">) {
  return <td className={cn("px-3 py-2 text-text", className)} {...props} />;
}

/**
 * A column heading that sorts, rendered as a link.
 *
 * A <Link>, not a button, for the same reason Pagination uses links: each sort
 * is a distinct URL, so it can be bookmarked and shared, the back button works,
 * and it functions with JavaScript off. It also means the SERVER does the
 * sorting -- which is the point. Sorting the rows a page happens to hold would
 * order a slice of the catalogue while looking authoritative, and be confidently
 * wrong the moment there is a second page.
 *
 * `aria-sort` on the <th> is what tells a screen reader which column is sorted
 * and which way; the arrow is aria-hidden because it would otherwise be
 * announced as punctuation on top of that.
 *
 * `page` is deliberately NOT carried across: re-sorting puts you on page 1,
 * because staying on page 4 of a newly-ordered list shows rows you never asked
 * for.
 */
export function SortableTH({
  column,
  label,
  sort,
  direction,
  basePath,
  params,
  className,
}: {
  column: string;
  label: string;
  /** The column currently sorted, straight from the URL. */
  sort: string;
  direction: "asc" | "desc";
  basePath: string;
  /** Filters to preserve. Omit `page` -- see above. */
  params?: Record<string, string | undefined>;
  className?: string;
}) {
  const active = sort === column;
  // A fresh column always starts ascending; the active one flips.
  const next = active && direction === "asc" ? "desc" : "asc";

  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) if (v) query.set(k, v);
  query.set("sort", column);
  query.set("direction", next);

  return (
    <TH
      aria-sort={
        active ? (direction === "asc" ? "ascending" : "descending") : "none"
      }
      className={className}
    >
      <Link
        href={`${basePath}?${query}`}
        className={cn(
          "inline-flex items-center gap-1 transition-colors motion-reduce:transition-none",
          active ? "text-text" : "hover:text-text",
        )}
      >
        {label}
        <span aria-hidden="true" className={active ? "text-accent" : "opacity-0"}>
          {active && direction === "desc" ? "▾" : "▴"}
        </span>
      </Link>
    </TH>
  );
}
