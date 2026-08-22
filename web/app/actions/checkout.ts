"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError, createPaymentIntent, placeOrder } from "@/lib/api";
import { getSession } from "@/lib/session";

/**
 * Placing an order. Address actions live in ./address.ts.
 *
 * As with the cart actions, each of these verifies the session itself -- a
 * Server Action is a directly reachable POST endpoint, not a private function
 * the UI happens to call.
 */

export type CheckoutState = { error?: string };

const SIGNED_OUT = "Please sign in to continue.";

export async function placeOrderAction(
  _prev: CheckoutState,
  formData: FormData,
): Promise<CheckoutState> {
  const token = await getSession();
  if (!token) return { error: SIGNED_OUT };

  const shipping = Number(formData.get("shipping_address_id"));
  // "Billing same as shipping" is the common case, so the form omits the field
  // entirely and it falls back rather than forcing a second identical choice.
  const billing = Number(formData.get("billing_address_id")) || shipping;

  if (!shipping) return { error: "Choose a delivery address." };

  let orderId: number;
  try {
    const order = await placeOrder(token, shipping, billing);
    orderId = order.id;
  } catch (error) {
    if (error instanceof ApiError) {
      // 409 means stock ran out between adding to the cart and paying -- the
      // cart's stock check is a courtesy, not a reservation, and checkout is
      // the authority (Section 6.7). The cart is left intact so the shopper can
      // adjust rather than losing everything.
      return { error: error.message };
    }
    throw error;
  }

  // The cart is now empty and stock has moved, so anything showing either is
  // stale.
  revalidatePath("/cart");
  revalidatePath("/", "layout");

  // Outside the try: redirect() signals by throwing.
  //
  // To the PAYMENT page, not the receipt. Placing the order also opened a
  // PaymentIntent (Phase 5 task 2), so the next thing the customer owes us is a
  // card -- and /orders/{id}/pay is the URL that resumes it if they wander off.
  redirect(`/orders/${orderId}/pay`);
}

/**
 * Called once the browser has seen Stripe accept the card.
 *
 * **Why this exists at all.** Payment is confirmed by Stripe talking to the
 * WEBHOOK, server to server. The browser never hears about that, and Next.js
 * caches rendered pages client-side -- so the receipt rendered at the instant of
 * redirect (order still pending, cart still full) was being served back
 * afterwards, saying "nothing has been charged" about an order that was paid,
 * beside a cart badge counting goods that were gone.
 *
 * Two things fix it, and both have to happen on the SERVER:
 *
 * 1. `createPaymentIntent` re-retrieves the intent from Stripe, so payments.status
 *    reflects reality immediately rather than waiting for the webhook. Note what
 *    this does NOT do: it does not mark the order paid. Only the webhook may do
 *    that, because only Stripe can be trusted to say money moved and the browser
 *    is the one party with a reason to lie about it. What the customer sees in
 *    the gap is "Payment received - confirming your order", which is true.
 *
 * 2. `revalidatePath('/', 'layout')` throws away the cached payloads for every
 *    route under the root layout -- which is what the header cart badge lives
 *    in, and why the badge and the page body could disagree with each other.
 *
 * Errors are swallowed on purpose. The customer's money has already moved; the
 * webhook will settle the order regardless, and failing here would show an alarm
 * about a payment that actually succeeded.
 */
export async function paymentSettledAction(orderId: number): Promise<void> {
  const token = await getSession();
  if (!token) return;

  try {
    await createPaymentIntent(token, orderId);
  } catch {
    /* the webhook is the authority; this is only to make the page truthful sooner */
  }

  revalidatePath(`/orders/${orderId}`);
  revalidatePath("/cart");
  revalidatePath("/", "layout");
}