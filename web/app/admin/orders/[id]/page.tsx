import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { OrderStatus } from "@/components/order-status";
import { OrderStatusActions } from "@/components/order-status-actions";
import { CopyButton } from "@/components/copy-button";
import { PrintButton } from "@/components/print-button";
import { OrderTotals } from "@/components/order-totals";
import { Card, CardBody } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ApiError, getAdminOrder } from "@/lib/api";
import type { Address } from "@/lib/api";
import { formatMoney, postalAddress } from "@/lib/format";
import { getSession } from "@/lib/session";

/**
 * One order, as the vendor sees it.
 *
 * Reuses OrderTotals and OrderStatus from the storefront rather than restyling
 * them -- Section 4.3's point about the two halves being one product is easiest
 * to keep true by literally sharing the components.
 *
 * Line items show the SNAPSHOT name and price. The vendor packing this box needs
 * what was actually bought and charged, not what the product is called today.
 */
export default async function AdminOrderPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const token = await getSession();
  if (!token) redirect("/login");

  const { id } = await params;
  const orderId = Number(id);
  if (!Number.isInteger(orderId)) notFound();

  let order;
  try {
    order = await getAdminOrder(token, orderId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && [403, 404].includes(error.status)) notFound();
    throw error;
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <Link
        href="/admin/orders"
        className="font-body text-xs uppercase tracking-wide text-muted hover:text-text print:hidden"
      >
        &larr; All orders
      </Link>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
        <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
          Order #{order.id}
        </h1>
        <div className="flex items-center gap-3">
          <OrderStatus status={order.status} />
          <PrintButton label="Print packing slip" />
        </div>
      </div>
      <p className="mt-2 font-body text-sm text-muted">
        Placed{" "}
        {new Date(order.created_at).toLocaleString(undefined, {
          year: "numeric",
          month: "long",
          day: "numeric",
          hour: "numeric",
          minute: "2-digit",
        })}
      </p>

      {/* A control surface, not part of the document. It advances the order; a
          packing slip that carries the buttons for doing so reads as an
          instruction to the customer. */}
      <section className="mt-8 rounded-md border border-border bg-surface p-6 print:hidden">
        <h2 className="font-body text-sm uppercase tracking-tight text-muted">
          Advance this order
        </h2>
        <div className="mt-4">
          <OrderStatusActions
            orderId={order.id}
            allowed={order.allowed_transitions}
        evidenceRequired={order.evidence_required}
          shipment={order.shipment}
        />
        </div>
      </section>

      <div className="mt-10 grid gap-10 lg:grid-cols-[1fr_18rem]">
        <div>
          <h2 className="font-body text-sm uppercase tracking-tight text-muted">
            Items
          </h2>
          <div className="mt-4 overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH>Product</TH>
                  <TH className="text-right">Unit price</TH>
                  <TH className="text-right">Qty</TH>
                  <TH className="text-right">Line total</TH>
                </TR>
              </THead>
              <TBody>
                {order.items.map((item) => (
                  <TR key={item.id}>
                    <TD>{item.product_name_snapshot}</TD>
                    <TD className="text-right">
                      {formatMoney(item.unit_price_snapshot)}
                    </TD>
                    <TD className="text-right">{item.quantity}</TD>
                    <TD className="text-right font-display">
                      {formatMoney(
                        // Server-computed money everywhere else; this one
                        // multiplication is safe because both operands are exact
                        // 2dp decimals and quantity is an integer -- no rate, no
                        // rounding. Anything with a rate stays on the server.
                        (
                          Number(item.unit_price_snapshot) * item.quantity
                        ).toFixed(2),
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </div>

          <div className="mt-10 grid gap-8 sm:grid-cols-3">
            <div>
              <h2 className="font-body text-sm uppercase tracking-tight text-muted">
                Customer
              </h2>
              <p className="mt-2 font-body text-sm text-text">
                {order.user_full_name}
              </p>
              <a
                href={`mailto:${order.user_email}`}
                className="font-body text-sm text-muted underline hover:text-text"
              >
                {order.user_email}
              </a>
            </div>
            <div>
              <AddressBlock title="Ship to" address={order.shipping_address} />
              {/* Only on "Ship to". Nothing gets posted to a billing address, so
                  a copy button there would be an invitation to a mis-shipment. */}
              <CopyButton
                className="mt-2 print:hidden"
                label="Copy address"
                text={postalAddress(order.user_full_name, order.shipping_address)}
              />
            </div>
            <AddressBlock title="Bill to" address={order.billing_address} />
          </div>
        </div>

        <aside>
          <Card>
            <CardBody>
              <OrderTotals
                subtotal={order.subtotal}
                tax={order.tax}
                shippingCost={order.shipping_cost}
                total={order.total}
              />
            </CardBody>
          </Card>
        </aside>
      </div>
    </main>
  );
}

function AddressBlock({ title, address }: { title: string; address: Address }) {
  return (
    <div>
      <h2 className="font-body text-sm uppercase tracking-tight text-muted">
        {title}
      </h2>
      <address className="mt-2 font-body text-sm not-italic text-text">
        {address.line1}
        {address.line2 && (
          <>
            <br />
            {address.line2}
          </>
        )}
        <br />
        {[address.city, address.state, address.postal_code]
          .filter(Boolean)
          .join(", ")}
        <br />
        {address.country}
      </address>
    </div>
  );
}
