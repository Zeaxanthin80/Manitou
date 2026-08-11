import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { buttonClasses } from "@/components/ui/button";
import { ApiError, listAdminProducts, listCategories } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatMoney } from "@/lib/format";
import { getSession } from "@/lib/session";

/**
 * Product list.
 *
 * Shows inactive products too -- that asymmetry with GET /products is the entire
 * reason the admin endpoint exists. A hidden product the vendor cannot find is a
 * hidden product they cannot unhide.
 */
export default async function AdminProductsPage() {
  const token = await getSession();
  if (!token) redirect("/login");

  let products, categories;
  try {
    [products, categories] = await Promise.all([
      listAdminProducts(token),
      listCategories(),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && error.status === 403) notFound();
    throw error;
  }

  const categoryName = new Map(categories.map((c) => [c.id, c.name]));

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
          Products
        </h1>
        <Link href="/admin/products/new" className={buttonClasses()}>
          New product
        </Link>
      </div>

      {products.total === 0 ? (
        <p className="mt-10 font-body text-base text-muted">
          No products yet. Create the first one.
        </p>
      ) : (
        <div className="mt-8 overflow-x-auto">
          <Table>
            <THead>
              <TR>
                <TH>Product</TH>
                <TH>Category</TH>
                <TH className="text-right">Price</TH>
                <TH className="text-right">Variants</TH>
                <TH className="text-right">Stock</TH>
                <TH>Visibility</TH>
              </TR>
            </THead>
            <TBody>
              {products.items.map((p) => {
                const stock = p.variants.reduce(
                  (n, v) => n + v.quantity_available,
                  0,
                );
                const lowStock = p.variants.some((v) => v.needs_reorder);
                return (
                  <TR key={p.id}>
                    <TD>
                      <Link
                        href={`/admin/products/${p.id}`}
                        className={cn(
                          "font-display text-sm uppercase tracking-tight hover:text-accent",
                          p.is_active ? "text-text" : "text-muted",
                        )}
                      >
                        {p.name}
                      </Link>
                      <span className="block font-body text-xs text-muted">
                        /{p.slug}
                      </span>
                    </TD>
                    <TD className="text-muted">
                      {categoryName.get(p.category_id) ?? "—"}
                    </TD>
                    <TD className="text-right">{formatMoney(p.base_price)}</TD>
                    <TD className="text-right">{p.variants.length}</TD>
                    <TD className="text-right">
                      <span className={lowStock ? "text-accent" : undefined}>
                        {stock}
                      </span>
                    </TD>
                    <TD>
                      {p.is_active ? (
                        <span className="font-body text-xs uppercase tracking-tight text-muted">
                          Visible
                        </span>
                      ) : (
                        <span className="rounded-sm border border-accent px-2 py-1 font-body text-xs uppercase tracking-tight text-accent">
                          Hidden
                        </span>
                      )}
                    </TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
        </div>
      )}
    </main>
  );
}
