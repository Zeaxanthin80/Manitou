import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { OrderStatus } from "@/components/order-status";
import { Pagination } from "@/components/pagination";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ApiError, listAdminOrders } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatMoney } from "@/lib/format";
import { getSession } from "@/lib/session";

const PER_PAGE = 20;

// Mirrors the ck_orders_status_valid CHECK constraint. These are filter values,
// not workflow rules -- the vendor may want to look at cancelled orders even
// though nothing can transition into one from here.
const FILTERS = [
  "pending",
  "paid",
  "shipped",
  "delivered",
  "cancelled",
  "refunded",
] as const;

/**
 * Order dashboard.
 *
 * A real <table>: this is tabular data, and the semantic element gives column
 * association to screen readers for free. Section 4.3 asks admin screens to be
 * denser than the storefront, which is exactly what a table is for.
 *
 * Filtering is done with links and a `?status=` param rather than a <select> and
 * client state. The server does the query, so the filter has to be in the URL
 * for the request to differ -- and it makes a filtered view shareable.
 */
export default async function AdminOrdersPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string; status?: string }>;
}) {
  const token = await getSession();
  if (!token) redirect("/login");

  const { page, status } = await searchParams;
  // An unknown ?status= would be silently ignored by the API and return
  // everything, which looks like a broken filter. 404 is honest.
  if (status && !FILTERS.includes(status as (typeof FILTERS)[number])) notFound();

  const parsed = Number(page);
  const current = Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
  const offset = (current - 1) * PER_PAGE;

  let orders;
  try {
    orders = await listAdminOrders(token, { limit: PER_PAGE, offset, status });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && error.status === 403) notFound();
    throw error;
  }

  const lastPage = Math.max(1, Math.ceil(orders.total / PER_PAGE));
  if (orders.total > 0 && current > lastPage) {
    const q = new URLSearchParams({ page: String(lastPage) });
    if (status) q.set("status", status);
    redirect(`/admin/orders?${q}`);
  }

  const filterHref = (s?: string) => (s ? `/admin/orders?status=${s}` : "/admin/orders");

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
          Orders
        </h1>
        <p className="font-body text-sm text-muted">
          {orders.total} {orders.total === 1 ? "order" : "orders"}
          {status ? ` with status ${status}` : ""}
        </p>
      </div>

      <nav aria-label="Filter by status" className="mt-6 flex flex-wrap gap-x-6 gap-y-2">
        {[undefined, ...FILTERS].map((s) => {
          const active = status === s;
          return (
            <Link
              key={s ?? "all"}
              href={filterHref(s)}
              aria-current={active ? "page" : undefined}
              className={cn(
                "font-body text-sm capitalize transition-colors motion-reduce:transition-none",
                active
                  ? "text-accent underline decoration-2 underline-offset-8"
                  : "text-muted hover:text-text",
              )}
            >
              {s ?? "All"}
            </Link>
          );
        })}
      </nav>

      {orders.items.length === 0 ? (
        <p className="mt-10 font-body text-base text-muted">
          No orders{status ? ` with status ${status}` : ""} yet.
        </p>
      ) : (
        <>
          <div className="mt-8 overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  {/* No width classes, deliberately -- the Products and
                      Inventory tables carry none either, and auto-layout
                      distributes six columns sensibly on its own. Constraining
                      some of them does not create room; it moves the slack into
                      whichever columns are left flexible, which is how Order
                      and Customer ended up with gaps beside them. */}
                  <TH>Order</TH>
                  <TH>Placed</TH>
                  <TH>Customer</TH>
                  <TH className="text-right">Items</TH>
                  {/* Extra left padding on Status only. Items is
                      right-aligned, so its digits sit hard against the next
                      column -- the gap that reads as generous elsewhere in this
                      table collapses to nothing right here. pl-6 is the token
                      scale's 24px, twice the base cell padding. */}
                  <TH className="pl-6">Status</TH>
                  <TH className="text-right">Total</TH>
                </TR>
              </THead>
              <TBody>
                {orders.items.map((o) => (
                  <TR key={o.id}>
                    <TD>
                      <Link
                        href={`/admin/orders/${o.id}`}
                        className="font-display text-sm uppercase tracking-tight text-text hover:text-accent"
                      >
                        #{o.id}
                      </Link>
                    </TD>
                    <TD className="whitespace-nowrap text-muted">
                      {new Date(o.created_at).toLocaleDateString(undefined, {
                        year: "numeric",
                        month: "short",
                        day: "numeric",
                      })}
                    </TD>
                    {/* max-w-0 truncate removed. THAT was what clipped the
                        address -- not a shortage of space -- and it was never
                        needed here: this table sits in overflow-x-auto, so a
                        pathologically long email scrolls inside the box instead
                        of breaking the page. title stays for that case. */}
                    <TD className="whitespace-nowrap" title={o.user_email}>
                      {o.user_email}
                    </TD>
                    <TD className="text-right">{o.item_count}</TD>
                    <TD className="pl-6">
                      <OrderStatus status={o.status} />
                    </TD>
                    <TD className="text-right font-display">
                      {formatMoney(o.total)}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </div>

          <Pagination
            total={orders.total}
            limit={orders.limit}
            offset={orders.offset}
            basePath="/admin/orders"
            params={{ status }}
          />
        </>
      )}
    </main>
  );
}
