import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { OrderTotals } from "@/components/order-totals";
import { Card, CardBody } from "@/components/ui/card";
import { ApiError, getOrder } from "@/lib/api";
import type { Address } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { getSession } from "@/lib/session";

/**
 * Order receipt.
 *
 * Everything shown here comes from the order's own snapshot columns, never from
 * the live product. If the vendor renames the item or raises the price tomorrow,
 * this page must keep showing what was actually bought and charged -- that is
 * exactly what order_items.product_name_snapshot and unit_price_snapshot are for
 * (PROJECT_PLAN Section 6.4).
 *
 * Someone else's order id returns 404 rather than 403, because 403 would confirm
 * the order exists. Same reasoning the API uses.
 */
export default async function OrderPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const token = await getSession();
  if (!token) redirect("/login");

  const orderId = Number(id);
  if (!Number.isInteger(orderId)) notFound();

  let order;
  try {
    order = await getOrder(token, orderId);
  } catch (error) {
    // 403 means suspended, not "not yours" -- this endpoint answers 404 for
    // someone else's order. Send them to sign in rather than 404ing.
    if (error instanceof ApiError && error.status === 403) redirect("/login");
    if (error instanceof ApiError && (error.status === 404 || error.status === 401)) {
      notFound();
    }
    throw error;
  }

  const placed = new Date(order.created_at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <main className="mx-auto max-w-4xl px-6 py-12">
      <p className="font-body text-xs uppercase tracking-tight text-muted">
        Order #{order.id} &middot; {placed}
      </p>
      <h1 className="mt-2 font-display text-2xl uppercase leading-none tracking-tight text-text">
        {orderHeading(order.status, order.payment_status)}
      </h1>
      <PaymentState
        orderId={order.id}
        orderStatus={order.status}
        paymentStatus={order.payment_status}
      />

      <div className="mt-10 grid gap-12 md:grid-cols-[1fr_18rem]">
        <div>
          <h2 className="font-body text-sm uppercase tracking-tight text-muted">
            Items
          </h2>
          <ul className="mt-4 flex flex-col">
            {order.items.map((item) => (
              <li
                key={item.id}
                className="flex items-baseline justify-between gap-4 border-b border-border py-3 font-body text-sm"
              >
                <span className="text-text">
                  {item.product_name_snapshot}
                  <span className="text-muted"> &times; {item.quantity}</span>
                </span>
                <span className="shrink-0 text-text">
                  {formatMoney(item.unit_price_snapshot)}
                </span>
              </li>
            ))}
          </ul>

          <div className="mt-8 grid gap-8 sm:grid-cols-2">
            <AddressBlock title="Delivered to" address={order.shipping_address} />
            <AddressBlock title="Billed to" address={order.billing_address} />
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
          <Link
            href="/"
            className="mt-4 inline-block font-body text-sm uppercase tracking-tight text-text underline"
          >
            Continue shopping
          </Link>
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

/**
 * What to tell the customer about money, from two signals rather than one.
 *
 * orders.status alone cannot express the state that matters most here: the gap
 * between a card being accepted by Stripe and the Phase 5 task 4 webhook saying
 * so. During that window the order is genuinely `pending` AND genuinely paid
 * for, and a page reading only `status` would have to either stay silent or
 * claim something it cannot know. Someone who has just typed a card number and
 * sees no acknowledgement assumes it failed and pays twice.
 *
 * "succeeded" here is Stripe's word for the PAYMENT, never for the order. Only
 * the webhook writes orders.status, because only Stripe can be trusted to say
 * money moved -- the browser is the one party with a reason to lie about it.
 */
function PaymentState({
  orderId,
  orderStatus,
  paymentStatus,
}: {
  orderId: number;
  orderStatus: string;
  paymentStatus: string | null;
}) {
  if (orderStatus === "cancelled" || orderStatus === "refunded") {
    return (
      <p className="mt-3 max-w-prose font-body text-base text-muted">
        This order was {orderStatus}.
      </p>
    );
  }

  if (orderStatus !== "pending") {
    return (
      <p className="mt-3 max-w-prose font-body text-base text-muted">
        Your order is {orderStatus}.
      </p>
    );
  }

  if (paymentStatus === "succeeded" || paymentStatus === "processing") {
    return (
      <p className="mt-3 max-w-prose font-body text-base text-muted">
        Payment received — we are confirming your order now.
      </p>
    );
  }

  // Nothing paid yet, and the order can still be paid for. Offer the way back
  // rather than leaving them to work out that a payment page exists.
  return (
    <p className="mt-3 max-w-prose font-body text-base text-muted">
      Your order is saved and nothing has been charged.{" "}
      <Link
        href={`/orders/${orderId}/pay`}
        className="text-text underline underline-offset-4"
      >
        Complete payment
      </Link>
      .
    </p>
  );
}

/**
 * The heading has to agree with the sentence under it.
 *
 * It used to be "Thank you" unconditionally, which sat directly above "Your
 * order is saved and nothing has been charged" -- two statements contradicting
 * each other on the same screen. That was survivable while an unpaid order was a
 * momentary state; it stopped being survivable once carts began surviving
 * abandonment, because a customer can now sit in the unpaid state indefinitely
 * and come back to a page thanking them for something they never bought.
 *
 * "Thank you" is reserved for money having actually arrived. Everything else
 * gets a label that describes where the order really is.
 */
function orderHeading(orderStatus: string, paymentStatus: string | null): string {
  if (orderStatus === "cancelled") return "Order cancelled";
  if (orderStatus === "refunded") return "Order refunded";
  if (orderStatus !== "pending") return "Thank you";
  // pending: thank them only once Stripe has taken the card, even though the
  // webhook has not yet promoted the order.
  return paymentStatus === "succeeded" || paymentStatus === "processing"
    ? "Thank you"
    : "Your order";
}
