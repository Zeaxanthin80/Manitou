"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError, createAddress, listAddresses, placeOrder } from "@/lib/api";
import type { Address } from "@/lib/api";
import { getSession } from "@/lib/session";

/**
 * Checkout and address actions.
 *
 * As with the cart actions, each of these verifies the session itself -- a
 * Server Action is a directly reachable POST endpoint, not a private function
 * the UI happens to call.
 */

export type CheckoutState = { error?: string };

const SIGNED_OUT = "Please sign in to continue.";

export async function currentAddresses(): Promise<Address[]> {
  const token = await getSession();
  if (!token) return [];
  try {
    return await listAddresses(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return [];
    throw error;
  }
}

export async function addAddressAction(
  _prev: CheckoutState,
  formData: FormData,
): Promise<CheckoutState> {
  const token = await getSession();
  if (!token) return { error: SIGNED_OUT };

  const text = (key: string) => String(formData.get(key) ?? "").trim();

  try {
    await createAddress(token, {
      line1: text("line1"),
      line2: text("line2") || null,
      city: text("city"),
      state: text("state") || null,
      postal_code: text("postal_code"),
      country: text("country"),
      // The API constrains this to a Literal, so a bad value is a 422 rather
      // than a database CHECK violation surfacing as a 500.
      type: "shipping",
      is_default: false,
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }

  revalidatePath("/checkout");
  return {};
}

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
