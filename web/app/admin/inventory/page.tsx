import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { InventoryTable } from "@/components/inventory-table";
import type { InventoryRow } from "@/components/inventory-table";
import { ApiError, listAdminProducts } from "@/lib/api";
import { cn } from "@/lib/cn";
import { getSession } from "@/lib/session";

/**
 * Stock across the whole catalog.
 *
 * Built from GET /admin/products rather than a new endpoint: that response
 * already carries every variant with its inventory, so a second endpoint would
 * be a second copy of the same join and the same needs_reorder rule. If the
 * catalog ever outgrows one page of results this flips, and inventory should get
 * its own paged, server-sorted endpoint.
 *
 * `needs_reorder` is computed by the API, never here. The threshold rule lives
 * in one place -- recomputing `qty <= reorder` client-side is how the storefront
 * and the portal end up disagreeing about what "low" means.
 */
export default async function InventoryPage({
  searchParams,
}: {
  searchParams: Promise<{ filter?: string }>;
}) {
  const token = await getSession();
  if (!token) redirect("/login");

  const { filter } = await searchParams;
  if (filter && !["low", "out"].includes(filter)) notFound();

  let products;
  try {
    products = await listAdminProducts(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && error.status === 403) notFound();
    throw error;
  }

  const all: InventoryRow[] = products.items.flatMap((p) =>
    p.variants.map((v) => ({
      variantId: v.id,
      sku: v.sku,
      variantName: v.variant_name,
      productId: p.id,
      productName: p.name,
      productSlug: p.slug,
      productActive: p.is_active,
      quantityAvailable: v.quantity_available,
      reorderLevel: v.reorder_level,
      needsReorder: v.needs_reorder,
    })),
  );

  // Sorted so the rows that need action are first, then by product for scanning.
  // Out of stock outranks merely low.
  const ordered = [...all].sort((a, b) => {
    const rank = (r: InventoryRow) =>
      r.quantityAvailable === 0 ? 0 : r.needsReorder ? 1 : 2;
    return (
      rank(a) - rank(b) ||
      a.productName.localeCompare(b.productName) ||
      a.sku.localeCompare(b.sku)
    );
  });

  const rows =
    filter === "out"
      ? ordered.filter((r) => r.quantityAvailable === 0)
      : filter === "low"
        ? ordered.filter((r) => r.needsReorder)
        : ordered;

  const lowCount = all.filter((r) => r.needsReorder).length;
  const outCount = all.filter((r) => r.quantityAvailable === 0).length;

  const FILTERS: { key?: string; label: string; count: number }[] = [
    { key: undefined, label: "All", count: all.length },
    { key: "low", label: "Needs reorder", count: lowCount },
    { key: "out", label: "Out of stock", count: outCount },
  ];

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
          Inventory
        </h1>
        <p className="font-body text-sm text-muted">
          {lowCount === 0
            ? "Everything above its reorder level."
            : `${lowCount} ${lowCount === 1 ? "variant needs" : "variants need"} reordering.`}
        </p>
      </div>

      <nav aria-label="Filter stock" className="mt-6 flex flex-wrap gap-x-6 gap-y-2">
        {FILTERS.map((f) => {
          const active = filter === f.key;
          return (
            <Link
              key={f.label}
              href={f.key ? `/admin/inventory?filter=${f.key}` : "/admin/inventory"}
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
        have. Checkout decrements it automatically as orders are placed.
      </p>

      <InventoryTable rows={rows} />
    </main>
  );
}
