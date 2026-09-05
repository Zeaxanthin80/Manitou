import { Hero } from "@/components/hero";
import { ProductCard } from "@/components/product-card";
import { SeriesStrip } from "@/components/series-strip";
import { listProducts } from "@/lib/api";

/**
 * Home: hero, series strip, catalogue.
 *
 * An async Server Component -- the fetches happen on the server, so the HTML
 * arrives complete. Section 3 cites SEO as a reason for Next.js, and this is
 * where that pays off: crawlers see products, not an empty shell.
 *
 * **Phase 7 replaced the opening.** Through Phase 3 this page led with the store
 * name at 44px over the tagline -- "one big, quiet statement" -- and that was
 * right until a wordmark landed in the header directly above it, at which point
 * the page said its own name twice before showing a product. The hero and the
 * strip are the replacement; the reasoning is in `hero.tsx`. The tagline is
 * still in the footer, where `store.tagline` always had its second home.
 *
 * Each section carries its own content column rather than the page setting one,
 * because the hero is the one thing here that is meant to run edge to edge.
 */
export default async function Home() {
  const page = await listProducts({ limit: 24 });

  return (
    <main>
      <Hero />
      <SeriesStrip />

      <section
        aria-labelledby="catalogue-heading"
        className="mx-auto max-w-6xl px-6 py-12"
      >
        <h2
          id="catalogue-heading"
          className="font-body text-xs uppercase tracking-tight text-muted"
        >
          {page.total} {page.total === 1 ? "product" : "products"}
        </h2>

        {page.items.length === 0 ? (
          <p className="mt-6 font-body text-base text-muted">
            Nothing here yet. Add a product from the vendor portal.
          </p>
        ) : (
          <div className="mt-6 grid grid-cols-2 gap-6 lg:grid-cols-3">
            {page.items.map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
