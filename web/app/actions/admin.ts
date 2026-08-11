"use server";

import { revalidatePath } from "next/cache";

import { ApiError, updateOrderStatus } from "@/lib/api";
import { currentUser } from "@/app/actions/auth";
import { getSession } from "@/lib/session";

/**
 * Vendor actions.
 *
 * Every one re-checks the session AND the role. The admin layout already gates
 * the pages, but a Server Action is a directly reachable POST endpoint -- a
 * layout renders UI, it does not stand between a request and this function. The
 * API's require_admin is still the real authority; this just fails early with a
 * message the portal can display instead of a raw 403.
 */

export type AdminActionState = { error?: string; ok?: string };

async function adminToken(): Promise<{ token?: string; error?: string }> {
  const token = await getSession();
  if (!token) return { error: "Your session expired. Please sign in again." };
  const user = await currentUser();
  if (!user) return { error: "Your session expired. Please sign in again." };
  if (user.role !== "admin") return { error: "Admin privileges required." };
  return { token };
}

export async function updateOrderStatusAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };

  const id = Number(formData.get("order_id"));
  const status = String(formData.get("status") ?? "");
  if (!id || !status) return { error: "Nothing to update." };

  try {
    await updateOrderStatus(token, id, status);
  } catch (err) {
    // A 409 here means the workflow forbids the move -- most likely because
    // someone else already advanced this order while the page was open. The
    // API's message names the current status, so it is shown as written.
    if (err instanceof ApiError) {
      // Revalidate even though nothing was written. A 409 means this page is
      // displaying a status that is no longer true, so the buttons it is
      // offering are wrong -- without this the vendor reads "cannot change a
      // cancelled order" while still looking at a "Mark paid" button.
      if (err.status === 409) revalidatePath(`/admin/orders/${id}`);
      return { error: err.message };
    }
    throw err;
  }

  revalidatePath(`/admin/orders/${id}`);
  revalidatePath("/admin/orders");
  return { ok: `Order #${id} is now ${status}.` };
}
