import Link from "next/link";
import { notFound } from "next/navigation";

import { ProductCard } from "@/components/product-card";
import { ApiError, getCategory, listCategories, listProducts } from "@/lib/api";

/**
 * Category listing, at either level of the tree.
 *
 * The API's category filter is recursive, so a parent shows everything beneath
 * it -- the WITH RECURSIVE CTE from Phase 2 task 2 surfacing in the UI. That is
 * what makes a two-level tree browsable from the top: T-Shirts lists every tee
 * across every series, and each series page lists only its own.
 *
 * The page shows where it sits: a parent link above the name when this is a
 * series, and a row of series links beneath it when this is a type. Both come
 * from the same categories list the header already fetches; nothing new is
 * stored, and a flat tree simply renders neither.
 */
export default async function CategoryPage({
  // params is a Promise in this version of Next.js -- it must be awaited.
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  // Only the FETCH is guarded, and the JSX is built after it -- the same shape
  // every admin page uses. Returning JSX from inside the try looked equivalent
  // and is not: React does not render a component when the element is created,
  // so a render-time error escapes the catch entirely and the handler below
  // would quietly never see it. An error boundary is what catches those.
  let category;
  let page;
  let all;
  try {
    [category, page, all] = await Promise.all([
      getCategory(slug),
      listProducts({ category: slug, limit: 24 }),
      listCategories(),
    ]);
  } catch (error) {
    // A 404 from the API becomes a 404 page, not a 500. Anything else is a real
    // failure and should surface as one.
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const parent = all.find((c) => c.id === category.parent_id) ?? null;
  const children = all.filter((c) => c.parent_id === category.id);

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      {parent && (
        <Link
          href={`/categories/${parent.slug}`}
          className="font-body text-xs uppercase tracking-wide text-muted hover:text-text"
        >
          &larr; {parent.name}
        </Link>
      )}

      <h1 className="mt-4 font-display text-2xl uppercase leading-none tracking-tight text-text">
        {category.name}
      </h1>
      <p className="mt-3 font-body text-sm text-muted">
        {page.total} {page.total === 1 ? "product" : "products"}
      </p>

      {children.length > 0 && (
        // Nav-styled rather than button-styled: these narrow the list, they do
        // not act on it. The row scrolls on a phone instead of wrapping, the
        // same call the header makes.
        <nav aria-label="Series" className="mt-6 overflow-x-auto">
          <ul className="flex flex-nowrap gap-3">
            {children.map((c) => (
              <li key={c.id} className="shrink-0">
                <Link
                  href={`/categories/${c.slug}`}
                  className="block rounded-full border border-border px-4 py-1 font-body text-sm text-text transition-colors hover:bg-background motion-reduce:transition-none"
                >
                  {c.name}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      )}

      {page.items.length === 0 ? (
        <p className="mt-8 font-body text-base text-muted">
          Nothing here yet.
        </p>
      ) : (
        <div className="mt-8 grid grid-cols-2 gap-6 lg:grid-cols-3">
          {page.items.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      )}
    </main>
  );
}
