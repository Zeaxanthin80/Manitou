import { notFound } from "next/navigation";

import { ProductCard } from "@/components/product-card";
import { ApiError, getCategory, listProducts } from "@/lib/api";

/** Category listing. The API's category filter is recursive, so a parent
 *  category shows everything beneath it -- the WITH RECURSIVE CTE from Phase 2
 *  task 2 surfacing in the UI. */
export default async function CategoryPage({
  // params is a Promise in this version of Next.js -- it must be awaited.
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  try {
    const [category, page] = await Promise.all([
      getCategory(slug),
      listProducts({ category: slug, limit: 24 }),
    ]);

    return (
      <main className="mx-auto max-w-6xl px-6 py-12">
        <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
          {category.name}
        </h1>
        <p className="mt-4 font-body text-xs uppercase tracking-tight text-muted">
          {page.total} {page.total === 1 ? "product" : "products"}
        </p>
        <div className="mt-6 grid grid-cols-2 gap-6 lg:grid-cols-3">
          {page.items.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      </main>
    );
  } catch (error) {
    // A 404 from the API becomes a 404 page, not a 500. Anything else is a real
    // failure and should surface as one.
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
}
