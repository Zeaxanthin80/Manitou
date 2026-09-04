import { FeaturedSeries } from "@/components/featured-series";
import { ProductCard } from "@/components/product-card";
import { listProducts } from "@/lib/api";
import { storeConfig } from "@/lib/store-config";

/** Catalogue. An async Server Component -- the fetch happens on the server, so
 *  the HTML arrives complete. Section 3 cites SEO as a reason for Next.js, and
 *  this is where that pays off: crawlers see products, not an empty shell. */
export default async function Home() {
  const page = await listProducts({ limit: 24 });

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      {/* Studio leads with one big, quiet statement and a lot of air around it.
          text-3xl is 44px from the token scale -- the size Archivo Black was
          chosen for.

          It steps down to text-2xl below 769px because 44px does not fit. The
          store name is twelve letters, which measures 366px in Archivo Black at
          tracking-tight, against the 327px a 375px screen leaves inside px-6 --
          so the heading ran off the right edge and took the whole page into
          horizontal scroll with it. `max-w-2xl` does not help: it caps the BOX,
          and a single unbreakable word overflows the box rather than wrapping.

          The fix is a smaller step on the same scale, not a clamp() or an
          arbitrary size -- 32px measures 265px and fits with room to spare. A
          clone with a longer name than this still needs checking at 375px;
          nothing here can know how long a name is. */}
      <h1 className="max-w-2xl font-display text-2xl uppercase leading-none tracking-tight text-text wide:text-3xl">
        {storeConfig.store.name}
      </h1>
      <p className="mt-4 max-w-prose font-body text-base text-muted">
        {storeConfig.store.tagline}
      </p>

      {/* Merchandising, above the catalogue. It reads store-config itself and
          renders nothing when no series is featured, so this stays one line and
          the page keeps its old shape for a store that leads with nothing. */}
      <FeaturedSeries />

      <p className="mt-12 font-body text-xs uppercase tracking-tight text-muted">
        {page.total} {page.total === 1 ? "product" : "products"}
      </p>

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
    </main>
  );
}
