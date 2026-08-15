import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Pagination } from "@/components/pagination";
import { SortableTH, Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { buttonClasses } from "@/components/ui/button";
import {
  ApiError,
  listAdminProducts,
  listCategories,
  type ProductSort,
  type SortDirection,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatMoney } from "@/lib/format";
import { getSession } from "@/lib/session";

const PER_PAGE = 20;

const SORTS: { column: ProductSort; label: string; className?: string }[] = [
  { column: "name", label: "Product" },
  { column: "category", label: "Category" },
  { column: "price", label: "Price", className: "text-right" },
  { column: "variants", label: "Variants", className: "text-right" },
  { column: "stock", label: "Stock", className: "text-right" },
  { column: "visibility", label: "Visibility" },
];

/**
 * Product list.
 *
 * Shows inactive products too -- that asymmetry with GET /products is the entire
 * reason the admin endpoint exists. A hidden product the vendor cannot find is a
 * hidden product they cannot unhide.
 *
 * Sorting, filtering and paging are all URL state handled by the API. None of it
 * is client state: the server runs the query, so the parameters have to be in the
 * URL for the request to differ at all -- and it makes any view shareable. Same
 * reasoning as the order dashboard's `?status=`.
 */
export default async function AdminProductsPage({
  searchParams,
}: {
  searchParams: Promise<{
    page?: string;
    sort?: string;
    direction?: string;
    category?: string;
  }>;
}) {
  const token = await getSession();
  if (!token) redirect("/login");

  const sp = await searchParams;

  // Validated here rather than passed through: an unknown value would be a 422
  // from the API, and a broken URL should show the list, not an error page.
  const sort = (SORTS.find((s) => s.column === sp.sort)?.column ??
    "name") as ProductSort;
  const direction: SortDirection = sp.direction === "desc" ? "desc" : "asc";
  const category = sp.category ? Number(sp.category) : undefined;
  if (sp.category && !Number.isInteger(category)) notFound();

  const page = Math.max(1, Number(sp.page) || 1);
  const offset = (page - 1) * PER_PAGE;

  let products, categories;
  try {
    [products, categories] = await Promise.all([
      listAdminProducts(token, {
        limit: PER_PAGE,
        offset,
        sort,
        direction,
        category,
      }),
      listCategories(),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && error.status === 403) notFound();
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const categoryName = new Map(categories.map((c) => [c.id, c.name]));

  // Carried onto every sort link and page link. `page` is absent on purpose:
  // re-sorting or changing filter returns you to page 1, because staying on
  // page 4 of a newly-ordered list shows rows nobody asked for.
  const carried = {
    sort,
    direction,
    category: category !== undefined ? String(category) : undefined,
  };

  const categoryHref = (id?: number) => {
    const q = new URLSearchParams({ sort, direction });
    if (id !== undefined) q.set("category", String(id));
    return `/admin/products?${q}`;
  };

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

      {/* Links rather than a <select>: the server runs the query, so the choice
          has to be in the URL. It also makes "all the candles" a shareable
          address, which matters more as a catalogue grows. */}
      <nav aria-label="Filter by category" className="mt-6 flex flex-wrap gap-2">
        {[{ id: undefined, name: "All" }, ...categories].map((c) => {
          const active = category === c.id;
          return (
            <Link
              key={c.id ?? "all"}
              href={categoryHref(c.id)}
              aria-current={active ? "true" : undefined}
              className={cn(
                "rounded-sm border px-3 py-1 font-body text-xs uppercase tracking-tight transition-colors motion-reduce:transition-none",
                active
                  ? "border-accent text-accent"
                  : "border-border text-muted hover:text-text",
              )}
            >
              {c.name}
            </Link>
          );
        })}
      </nav>

      {products.total === 0 ? (
        <p className="mt-10 font-body text-base text-muted">
          {category !== undefined
            ? "No products in this category."
            : "No products yet. Create the first one."}
        </p>
      ) : (
        <>
          <div className="mt-8 overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  {SORTS.map((s) => (
                    <SortableTH
                      key={s.column}
                      column={s.column}
                      label={s.label}
                      sort={sort}
                      direction={direction}
                      basePath="/admin/products"
                      params={carried}
                      className={s.className}
                    />
                  ))}
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
                      <TD className="text-right">
                        {formatMoney(p.base_price)}
                      </TD>
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

          <Pagination
            total={products.total}
            limit={products.limit}
            offset={products.offset}
            basePath="/admin/products"
            params={carried}
          />
        </>
      )}
    </main>
  );
}
