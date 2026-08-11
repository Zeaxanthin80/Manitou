"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError, placeOrder } from "@/lib/api";
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
  redirect(`/orders/${orderId}`);
}
