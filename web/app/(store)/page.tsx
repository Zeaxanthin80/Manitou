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
          chosen for. */}
      <h1 className="max-w-2xl font-display text-3xl uppercase leading-none tracking-tight text-text">
        {storeConfig.store.name}
      </h1>
      <p className="mt-4 max-w-prose font-body text-base text-muted">
        Printed in small runs and restocked when they sell out.
      </p>

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
