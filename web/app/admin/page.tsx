import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { OrderStatus } from "@/components/order-status";
import { Card, CardBody } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ApiError, getAdminSummary } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { getSession } from "@/lib/session";

/**
 * Sales and stock at a glance.
 *
 * Every number here is aggregated by Postgres and arrives ready to print. This
 * page performs no arithmetic at all -- not even a total -- for the same reason
 * the cart quotes its own tax: money math lives in exactly one place, and a
 * dashboard that recomputes figures is a dashboard that will eventually disagree
 * with the orders it is summarising.
 */
export default async function AdminSummaryPage() {
  const token = await getSession();
  if (!token) redirect("/login");

  let s;
  try {
    s = await getAdminSummary(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && error.status === 403) notFound();
    throw error;
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
        Summary
      </h1>

      <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Revenue"
          value={formatMoney(s.revenue_all_time)}
          note={`${s.orders_counted} ${s.orders_counted === 1 ? "order" : "orders"} paid, shipped or delivered`}
        />
        <Stat
          label="Last 30 days"
          value={formatMoney(s.revenue_last_30_days)}
          note="Same basis, recent window"
        />
        <Stat
          label="Average order"
          value={formatMoney(s.average_order_value)}
          note="Across counted orders"
        />
        <Stat
          label="Awaiting payment"
          value={formatMoney(s.pending_value)}
          note={`${s.pending_count} pending ${s.pending_count === 1 ? "order" : "orders"}`}
          accent={s.pending_count > 0}
        />
      </div>

      <p className="mt-4 max-w-prose font-body text-xs text-muted">
        Revenue counts paid, shipped and delivered orders only — cancelled and
        refunded ones are excluded, and pending orders are shown separately
        because the money has not arrived yet.
      </p>

      <div className="mt-12 grid gap-12 lg:grid-cols-2">
        <section>
          <h2 className="font-body text-sm uppercase tracking-tight text-muted">
            Orders by status
          </h2>
          {s.by_status.length === 0 ? (
            <p className="mt-4 font-body text-sm text-muted">No orders yet.</p>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <Table>
                <THead>
                  <TR>
                    <TH>Status</TH>
                    <TH className="text-right">Orders</TH>
                    <TH className="text-right">Value</TH>
                  </TR>
                </THead>
                <TBody>
                  {s.by_status.map((row) => (
                    <TR key={row.status}>
                      <TD>
                        <Link href={`/admin/orders?status=${row.status}`}>
                          <OrderStatus status={row.status} />
                        </Link>
                      </TD>
                      <TD className="text-right">{row.count}</TD>
                      <TD className="text-right">{formatMoney(row.value)}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
          )}
        </section>

        <section>
          <h2 className="font-body text-sm uppercase tracking-tight text-muted">
            Best sellers
          </h2>
          {s.top_products.length === 0 ? (
            <p className="mt-4 font-body text-sm text-muted">
              Nothing sold yet.
            </p>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <Table>
                <THead>
                  <TR>
                    <TH>Product</TH>
                    <TH className="text-right">Units</TH>
                    <TH className="text-right">Revenue</TH>
                  </TR>
                </THead>
                <TBody>
                  {s.top_products.map((p) => (
                    <TR key={p.product_name}>
                      <TD>{p.product_name}</TD>
                      <TD className="text-right">{p.units}</TD>
                      <TD className="text-right">{formatMoney(p.revenue)}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <p className="mt-3 font-body text-xs text-muted">
                By units sold, excluding cancelled and refunded orders. Named as
                each item appeared on its receipt.
              </p>
            </div>
          )}
        </section>
      </div>

      <section className="mt-12">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <h2 className="font-body text-sm uppercase tracking-tight text-muted">
            Needs reordering
          </h2>
          <Link
            href="/admin/inventory"
            className="font-body text-sm text-muted underline hover:text-text"
          >
            Manage inventory
          </Link>
        </div>

        {s.low_stock.length === 0 ? (
          <p className="mt-4 font-body text-sm text-muted">
            Every variant is above its reorder level.
          </p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH>Product</TH>
                  <TH>SKU</TH>
                  <TH className="text-right">In stock</TH>
                  <TH className="text-right">Reorder at</TH>
                </TR>
              </THead>
              <TBody>
                {s.low_stock.map((v) => (
                  <TR key={v.variant_id}>
                    <TD>
                      <Link
                        href={`/admin/products/${v.product_id}`}
                        className="font-display text-sm uppercase tracking-tight text-text hover:text-accent"
                      >
                        {v.product_name}
                      </Link>
                      <span className="block font-body text-sm text-muted">
                        {v.variant_name}
                      </span>
                    </TD>
                    <TD className="text-muted">{v.sku}</TD>
                    <TD className="text-right">
                      <span
                        className={
                          v.quantity_available === 0 ? "text-accent" : undefined
                        }
                      >
                        {v.quantity_available}
                      </span>
                    </TD>
                    <TD className="text-right text-muted">{v.reorder_level}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </div>
        )}
      </section>
    </main>
  );
}

function Stat({
  label,
  value,
  note,
  accent,
}: {
  label: string;
  value: string;
  note: string;
  accent?: boolean;
}) {
  return (
    <Card>
      <CardBody>
        <p className="font-body text-xs uppercase tracking-wide text-muted">
          {label}
        </p>
        <p
          className={`mt-2 font-display text-2xl leading-none ${accent ? "text-accent" : "text-text"}`}
        >
          {value}
        </p>
        <p className="mt-2 font-body text-xs text-muted">{note}</p>
      </CardBody>
    </Card>
  );
}
