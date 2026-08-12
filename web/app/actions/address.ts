"use server";

import { revalidatePath } from "next/cache";

import { ApiError, createAddress, deleteAddress, listAddresses } from "@/lib/api";
import type { Address } from "@/lib/api";
import { getSession } from "@/lib/session";

/**
 * Address book.
 *
 * These live together rather than next to whichever page happens to call them:
 * checkout adds an address, the account page adds and removes them, and Phase 4
 * will read them again. One home, three callers.
 *
 * As everywhere else, each action checks the session itself -- a Server Action is
 * a directly reachable POST endpoint, not a private function the UI happens to
 * call.
 */

export type AddressState = { error?: string; ok?: boolean };

const SIGNED_OUT = "Please sign in to continue.";

export async function currentAddresses(): Promise<Address[]> {
  const token = await getSession();
  if (!token) return [];
  try {
    return await listAddresses(token);
  } catch (error) {
    // 403 too: a suspended account still holds a valid token.
    if (error instanceof ApiError && [401, 403].includes(error.status)) return [];
    throw error;
  }
}

export async function addAddressAction(
  _prev: AddressState,
  formData: FormData,
): Promise<AddressState> {
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
  revalidatePath("/account");
  return { ok: true };
}

export async function deleteAddressAction(
  _prev: AddressState,
  formData: FormData,
): Promise<AddressState> {
  const token = await getSession();
  if (!token) return { error: SIGNED_OUT };

  const id = Number(formData.get("address_id"));
  if (!id) return { error: "Nothing to remove." };

  try {
    await deleteAddress(token, id);
  } catch (error) {
    // 409 is the expected answer for an address a past order points at. The
    // API's sentence is written to be shown as-is, so it is not reworded here.
    if (error instanceof ApiError) return { error: error.message };
    throw error;
  }

  revalidatePath("/checkout");
  revalidatePath("/account");
  return { ok: true };
}
