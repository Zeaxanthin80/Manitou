import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { OrderTotals } from "@/components/order-totals";
import { Card, CardBody } from "@/components/ui/card";
import { ApiError, getOrder } from "@/lib/api";
import type { Address, OrderDetail } from "@/lib/api";
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

      <TrackingTimeline order={order} />

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

/**
 * Where the order is, as four steps.
 *
 * The transparency this phase exists for. Before it a customer saw a status
 * word and no dates, no carrier and no link -- and the word itself meant only
 * that somebody had clicked a button.
 *
 * Steps are derived from facts already on the order rather than from a status
 * string: `created_at` for Ordered, `payment_status` for Paid, and the shipment
 * for the last two. A status word can only ever say where the order is now;
 * these say when each thing happened, which is what somebody chasing a parcel
 * actually asked.
 */
function TrackingTimeline({ order }: { order: OrderDetail }) {
  const shipment = order.shipment;

  // Cancelled and refunded orders are not journeys. Showing a half-finished
  // progress bar under "Order cancelled" would read as a parcel still coming.
  if (order.status === "cancelled" || order.status === "refunded") return null;

  const paid =
    order.status !== "pending" ||
    order.payment_status === "succeeded" ||
    order.payment_status === "processing";

  const steps = [
    { label: "Ordered", at: order.created_at, done: true },
    { label: "Paid", at: paid ? order.created_at : null, done: paid },
    {
      // "Shipped", not "Dispatched". The order status badge on this same page
      // says `shipped`, and two words for one thing reads as two things.
      // `shipments.dispatched_at` keeps its name -- that is the schema, and the
      // moment a parcel leaves is genuinely a dispatch; this is the customer's
      // word for it.
      label: "Shipped",
      at: shipment?.dispatched_at ?? null,
      done: Boolean(shipment),
    },
    {
      label: "Delivered",
      at: shipment?.delivered_at ?? null,
      done: Boolean(shipment?.delivered_at),
    },
  ];

  return (
    <section className="mt-10">
      <h2 className="font-body text-sm uppercase tracking-tight text-muted">
        Tracking
      </h2>

      <ol className="mt-4 flex flex-col gap-3">
        {steps.map((step, i) => (
          <li key={step.label} className="relative flex items-baseline gap-3">
            {/* The connector, on every step but the last. Without it four dots
                in a column read as an unordered list rather than a sequence --
                the reader has to infer the ordering that the line simply
                states. Drawn behind the dot, which carries its own background
                so a hollow marker does not show the line through its middle. */}
            {i < steps.length - 1 && (
              <span
                aria-hidden
                // Centred, not offset by a guessed number. The dot is 8px, so
                // its centre is 4px -- and no INTEGER position centres a 1px
                // line under it: left-[3px] occupies 3-4px (centre 3.5, half a
                // pixel left) and left-1 occupies 4-5px (half a pixel right).
                // left-1 with -translate-x-1/2 lands it on 3.5-4.5, centred on
                // 4 exactly, and keeps working if the dot size ever changes.
                className="absolute bottom-[-0.875rem] left-1 top-[0.6rem] w-px -translate-x-1/2 bg-border"
              />
            )}
            <span
              aria-hidden
              className={
                step.done
                  ? "relative z-10 h-2 w-2 shrink-0 rounded-full bg-text"
                  : "relative z-10 h-2 w-2 shrink-0 rounded-full border border-border bg-background"
              }
            />
            <span
              className={
                step.done
                  ? "font-body text-sm text-text"
                  : "font-body text-sm text-muted"
              }
            >
              {step.label}
            </span>
            {step.at && (
              <span className="font-body text-xs text-muted">
                {new Date(step.at).toLocaleDateString(undefined, {
                  year: "numeric",
                  month: "long",
                  day: "numeric",
                })}
              </span>
            )}
          </li>
        ))}
      </ol>

      {shipment && shipment.events.length > 0 && (
        <ActivityList events={shipment.events} />
      )}

      {shipment && (
        <p className="mt-4 font-body text-sm text-muted">
          {shipment.carrier_name ?? "In transit"}
          {shipment.tracking_number && (
            <>
              {" \u00b7 "}
              {shipment.tracking_url ? (
                <a
                  href={shipment.tracking_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-text underline underline-offset-4 hover:text-accent"
                >
                  Track {shipment.tracking_number}
                </a>
              ) : (
                shipment.tracking_number
              )}
            </>
          )}
        </p>
      )}
    </section>
  );
}

/**
 * What the customer's words for each event are.
 *
 * The database vocabulary is written for the system: six exact strings a CHECK
 * constraint accepts. "Failed" is accurate and tells a customer nothing about
 * what to do -- "Delivery attempt failed" says the parcel is still coming, which
 * is the fact they actually need.
 *
 * `dispatched` is absent deliberately: the milestone bar above already says
 * Shipped with the same timestamp, and repeating it turns a timeline into a
 * duplicate.
 */
const ACTIVITY_LABELS: Record<string, string> = {
  in_transit: "In transit",
  out_for_delivery: "Out for delivery",
  delivered: "Delivered",
  failed: "Delivery attempt failed",
  returned: "Returned to sender",
};

/** Events worth the customer's attention. `failed` and `returned` are the ones
 *  that mean something has gone wrong and they may need to act. */
const ACTIVITY_ATTENTION = new Set(["failed", "returned"]);

/**
 * Every scan on the parcel, newest last.
 *
 * Sits BELOW the milestone bar rather than replacing it, because the two answer
 * different questions: the bar says where the order is in the process, this says
 * what is happening to the box. Merging them would put a hollow future
 * "Delivered" step in among things that have already happened.
 *
 * Before this, a customer whose delivery failed twice saw "Shipped" and silence.
 * The events were already in the payload -- the page simply ignored them.
 */
function ActivityList({
  events,
}: {
  events: NonNullable<OrderDetail["shipment"]>["events"];
}) {
  const shown = events.filter((e) => e.status in ACTIVITY_LABELS);
  if (shown.length === 0) return null;

  return (
    <div className="mt-6">
      <h3 className="font-body text-xs uppercase tracking-tight text-muted">
        Activity
      </h3>
      <ul className="mt-2 flex flex-col gap-1">
        {shown.map((e, i) => (
          <li key={i} className="font-body text-sm">
            <span
              className={
                ACTIVITY_ATTENTION.has(e.status) ? "text-accent" : "text-text"
              }
            >
              {ACTIVITY_LABELS[e.status]}
            </span>
            <span className="text-muted">
              {" \u00b7 "}
              {new Date(e.occurred_at).toLocaleString(undefined, {
                month: "short",
                day: "numeric",
                hour: "numeric",
                minute: "2-digit",
              })}
              {/* Who says so. Repetitive today, because every event is the store
                  clicking a button -- and that is exactly the point. It stops
                  being repetitive when carrier webhooks arrive, and a customer
                  can then tell "the shop marked this" from "UPS confirmed it". */}
              {e.source === "carrier" && " \u00b7 confirmed by the carrier"}
              {e.source === "admin" && " \u00b7 updated by the store"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
