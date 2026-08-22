import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { InventoryTable } from "@/components/inventory-table";
import { Pagination } from "@/components/pagination";
import {
  ApiError,
  listAdminInventory,
  type InventorySort,
  type SortDirection,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { getSession } from "@/lib/session";

const PER_PAGE = 50;

const SORTS: InventorySort[] = ["status", "product", "sku", "stock", "reorder"];

/**
 * Stock across the whole catalog, one row per variant.
 *
 * Reads GET /admin/inventory, not GET /admin/products. It used to derive from
 * the products response, which worked only while the whole catalog fitted in one
 * page: a row here is a VARIANT, and an endpoint that pages by product cannot
 * order or page variants. Sorting what one page happened to contain would order
 * a slice of the catalog while looking authoritative.
 *
 * `needs_reorder` is computed by the API, never here. The threshold rule lives in
 * one place -- on the Inventory model, as a hybrid_property, so the Python
 * boolean and the SQL used to sort and filter by it are the same expression.
 * Recomputing `qty <= reorder` client-side is how the storefront and the portal
 * end up disagreeing about what "low" means.
 *
 * low_count and out_count come from the API too, because they label the filter
 * links: counting the rows this page received would report the page rather than
 * the catalog, and "Out of stock (3)" would change as you paged.
 */
export default async function InventoryPage({
  searchParams,
}: {
  searchParams: Promise<{
    page?: string;
    filter?: string;
    sort?: string;
    direction?: string;
  }>;
}) {
  const token = await getSession();
  if (!token) redirect("/login");

  const sp = await searchParams;
  if (sp.filter && !["low", "out"].includes(sp.filter)) notFound();
  const filter = sp.filter as "low" | "out" | undefined;

  const sort = (SORTS.includes(sp.sort as InventorySort)
    ? sp.sort
    : "status") as InventorySort;
  const direction: SortDirection = sp.direction === "desc" ? "desc" : "asc";
  const page = Math.max(1, Number(sp.page) || 1);

  let data;
  try {
    data = await listAdminInventory(token, {
      limit: PER_PAGE,
      offset: (page - 1) * PER_PAGE,
      sort,
      direction,
      filter,
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && error.status === 403) notFound();
    throw error;
  }

  const rows = data.items.map((r) => ({
    variantId: r.variant_id,
    sku: r.sku,
    variantName: r.variant_name,
    productId: r.product_id,
    productName: r.product_name,
    productSlug: r.product_slug,
    productActive: r.product_active,
    quantityAvailable: r.quantity_available,
    quantityReserved: r.quantity_reserved,
    quantitySellable: r.quantity_sellable,
    reorderLevel: r.reorder_level,
    needsReorder: r.needs_reorder,
  }));

  // Every count here is catalog-wide, straight from the API. Deliberately NOT
  // `data.total` -- that is the count matching the ACTIVE filter, which is what
  // Pagination needs and the wrong number for a button offering a different one.
  // Using it would make "All (2)" appear while the Out of stock filter was on.
  const FILTERS: { key?: "low" | "out"; label: string; count: number }[] = [
    { key: undefined, label: "All", count: data.all_count },
    { key: "low", label: "Needs reorder", count: data.low_count },
    { key: "out", label: "Out of stock", count: data.out_count },
  ];

  const carried = { sort, direction, filter };

  const filterHref = (key?: "low" | "out") => {
    const q = new URLSearchParams({ sort, direction });
    if (key) q.set("filter", key);
    return `/admin/inventory?${q}`;
  };

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
          Inventory
        </h1>
        <p className="font-body text-sm text-muted">
          {data.low_count === 0
            ? "Everything above its reorder level."
            : `${data.low_count} ${data.low_count === 1 ? "variant needs" : "variants need"} reordering.`}
        </p>
      </div>

      <nav aria-label="Filter stock" className="mt-6 flex flex-wrap gap-x-6 gap-y-2">
        {FILTERS.map((f) => {
          const active = filter === f.key;
          return (
            <Link
              key={f.label}
              href={filterHref(f.key)}
              aria-current={active ? "page" : undefined}
              className={cn(
                "font-body text-sm transition-colors motion-reduce:transition-none",
                active
                  ? "text-accent underline decoration-2 underline-offset-8"
                  : "text-muted hover:text-text",
              )}
            >
              {f.label} ({f.count})
            </Link>
          );
        })}
      </nav>

      <p className="mt-6 max-w-prose font-body text-sm text-muted">
        Stock is an absolute count, not an adjustment — enter what you actually
        have, then press Save on that row. Nothing saves automatically. Checkout
        decrements it as orders are placed.
      </p>

      <InventoryTable
        rows={rows}
        sort={sort}
        direction={direction}
        params={carried}
      />

      <Pagination
        total={data.total}
        limit={data.limit}
        offset={data.offset}
        basePath="/admin/inventory"
        params={{ ...carried }}
      />
    </main>
  );
}
