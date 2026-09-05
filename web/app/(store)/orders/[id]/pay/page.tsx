import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { OrderTotals } from "@/components/order-totals";
import { PaymentForm } from "@/components/payment-form";
import { Card, CardBody } from "@/components/ui/card";
import { ApiError, createPaymentIntent, getOrder } from "@/lib/api";
import { getSession } from "@/lib/session";

/**
 * The payment step.
 *
 * A Server Component: it holds the session cookie, calls FastAPI, and passes
 * only the client secret down to the Client Component that mounts Stripe's
 * element. The browser never talks to the API, and the JWT never leaves here.
 *
 * A ROUTE rather than a step inside /checkout, because payment needs somewhere
 * to come back to. A customer who reloads, closes the tab, or hits a Stripe
 * outage has a URL that resumes the same payment -- which is what
 * POST /orders/{id}/payment-intent was built for, and what the API's own outage
 * message ("try again from your order page") promises.
 *
 * Reloading is safe by construction: the endpoint is create-or-retrieve, keyed
 * on the order, so a refresh returns the SAME intent rather than opening a
 * second one against the same order.
 */
export default async function PayPage({
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
    if (error instanceof ApiError && error.status === 403) redirect("/login");
    if (error instanceof ApiError && (error.status === 404 || error.status === 401)) {
      notFound();
    }
    throw error;
  }

  let intent;
  try {
    intent = await createPaymentIntent(token, orderId);
  } catch (error) {
    // 409 is OrderNotPayable: already paid, cancelled or refunded. Not an error
    // to show -- the customer asked to pay something that no longer needs
    // paying, and the receipt answers that better than a card form would.
    if (error instanceof ApiError && error.status === 409) {
      redirect(`/orders/${orderId}`);
    }
    // 502 means Stripe could not be reached. The order is safe and unpaid, so
    // send them to the receipt, which says so and offers this page again.
    if (error instanceof ApiError && error.status === 502) {
      redirect(`/orders/${orderId}`);
    }
    throw error;
  }

  // Already paid, or settling. The 409 guard above CANNOT catch this: it fires
  // on order.status, and the order stays `pending` until the task 4 webhook
  // exists -- so for the whole of task 3 an order can be paid at Stripe and
  // pending here at the same time. Reached by pressing Pay and reloading before
  // the redirect lands, which is an ordinary thing for an impatient customer to
  // do, not an edge case.
  //
  // Showing a card form here would invite a second payment for something already
  // bought. Stripe would refuse to confirm the intent twice, so no money is at
  // risk -- but the customer would be staring at a form that cannot work.
  //
  // "requires_action" is deliberately NOT in this list: that is a 3-D Secure
  // challenge in progress, and the form is exactly where it needs to resume.
  if (intent.status === "succeeded" || intent.status === "processing") {
    redirect(`/orders/${orderId}`);
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-12">
      <p className="font-body text-xs uppercase tracking-wide text-muted">
        Order #{order.id}
      </p>
      <h1 className="mt-2 font-display text-2xl uppercase leading-none tracking-tight text-text">
        Payment
      </h1>

      <div className="mt-10 grid gap-12 md:grid-cols-[1fr_18rem]">
        <div>
          <PaymentForm
            clientSecret={intent.client_secret}
            orderId={order.id}
            amount={intent.amount}
          />
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
            href="/cart"
            className="mt-4 inline-block font-body text-sm uppercase tracking-tight text-muted underline hover:text-text"
          >
            Back to cart
          </Link>
        </aside>
      </div>
    </main>
  );
}
