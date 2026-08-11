import Link from "next/link";

import { buttonClasses } from "@/components/ui/button";

/**
 * Offset pagination, rendered as real links.
 *
 * Links rather than buttons on purpose: each page is a distinct URL, so it can
 * be bookmarked, opened in a new tab, and reached with the back button. That
 * also means no JavaScript is required to page through history.
 *
 * Disabled edges render as plain text rather than a dead link -- there is no
 * such thing as a disabled <a>, and a link that goes nowhere is worse for a
 * screen reader than no link at all.
 */
export function Pagination({
  total,
  limit,
  offset,
  basePath,
}: {
  total: number;
  limit: number;
  offset: number;
  basePath: string;
}) {
  if (total <= limit) return null;

  const page = Math.floor(offset / limit) + 1;
  const pages = Math.ceil(total / limit);
  const href = (n: number) => `${basePath}?page=${n}`;

  const edge = "font-body text-sm uppercase tracking-tight";

  return (
    <nav
      aria-label="Pagination"
      className="mt-10 flex items-center justify-between gap-4"
    >
      {page > 1 ? (
        <Link href={href(page - 1)} className={buttonClasses({ variant: "ghost" })}>
          Previous
        </Link>
      ) : (
        <span className={`${edge} text-muted`}>Previous</span>
      )}

      <span className={`${edge} text-muted`} aria-current="page">
        Page {page} of {pages}
      </span>

      {page < pages ? (
        <Link href={href(page + 1)} className={buttonClasses({ variant: "ghost" })}>
          Next
        </Link>
      ) : (
        <span className={`${edge} text-muted`}>Next</span>
      )}
    </nav>
  );
}
