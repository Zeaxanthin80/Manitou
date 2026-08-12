"use server";

import { revalidatePath } from "next/cache";

import {
  ApiError,
  addCartItem,
  getCart,
  removeCartItem,
  updateCartItem,
} from "@/lib/api";
import type { Cart } from "@/lib/api";
import { getSession } from "@/lib/session";

/**
 * Cart mutations.
 *
 * Every one of these checks the session ITSELF. The Next.js docs are explicit
 * that a Server Action is a real POST endpoint reachable directly, not only
 * through your form -- so "the button was only rendered for signed-in users" is
 * not a control. Without the check here, an unauthenticated POST would reach
 * FastAPI with no token and 401, which is safe but produces a confusing error;
 * with a *stolen* form it would be worse. Check first, always.
 *
 * The API is still the real authority: cart items are scoped to the caller's own
 * cart by an ownership join (Phase 2 task 3), so even a valid token cannot touch
 * someone else's line.
 */

export type CartActionState = { error?: string };

const SIGNED_OUT = "Please sign in to use the cart.";

async function requireToken(): Promise<string | null> {
  return getSession();
}

/** Shared shape: run an API call with the session token, translate failures. */
async function mutate(
  fn: (token: string) => Promise<unknown>,
): Promise<CartActionState> {
  const token = await requireToken();
  if (!token) return { error: SIGNED_OUT };

  try {
    await fn(token);
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }

  // The cart is read by the /cart page and the header count. Both are Server
  // Components, so the server has to be told their data changed.
  revalidatePath("/cart");
  revalidatePath("/", "layout");
  return {};
}

export async function addToCartAction(
  _prev: CartActionState,
  formData: FormData,
): Promise<CartActionState> {
  const variantId = Number(formData.get("variant_id"));
  const quantity = Number(formData.get("quantity") ?? 1);
  if (!variantId) return { error: "Choose an option first." };
  return mutate((token) => addCartItem(token, variantId, quantity));
}

export async function updateQuantityAction(formData: FormData) {
  const itemId = Number(formData.get("item_id"));
  const quantity = Number(formData.get("quantity"));
  // quantity is capped at >= 1 by the API and by a CHECK constraint; removing a
  // line is DELETE, not quantity 0.
  await mutate((token) => updateCartItem(token, itemId, quantity));
}

export async function removeFromCartAction(formData: FormData) {
  const itemId = Number(formData.get("item_id"));
  await mutate((token) => removeCartItem(token, itemId));
}

/** The caller's cart, or null when signed out. */
export async function currentCart(): Promise<Cart | null> {
  const token = await getSession();
  if (!token) return null;
  try {
    return await getCart(token);
  } catch (error) {
    // An expired token -- or a suspended account, which answers 403 -- renders as
    // an empty cart rather than crashing the page.
    if (error instanceof ApiError && [401, 403].includes(error.status)) return null;
    throw error;
  }
}
