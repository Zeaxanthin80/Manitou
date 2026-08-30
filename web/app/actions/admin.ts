"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  ApiError,
  adminAnonymise,
  adminDisableTwoFactor,
  addProductImage,
  confirmUpload,
  requestUpload,
  addVariant,
  createProduct,
  deactivateProduct,
  deleteProductImage,
  dispatchOrder,
  recheckOrderPayment,
  recordShipmentEvent,
  sendAdminPasswordReset,
  updateAdminUser,
  updateOrderStatus,
  updateProduct,
  updateInventory,
  updateProductImage,
  updateVariant,
} from "@/lib/api";
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

/**
 * What each outcome means to a vendor, in their words rather than the API's.
 *
 * Kept here rather than in the component so the sentence lives beside the action
 * that produces it. "mirrored" deliberately does NOT say "not paid": a payment
 * can be mid-authentication, and telling a vendor an order is unpaid when the
 * customer is halfway through 3-D Secure invites them to cancel it.
 */
const RECHECK_MESSAGE: Record<string, string> = {
  confirmed: "Payment confirmed — the order is now paid.",
  already_paid: "Already paid. Nothing to change.",
  conflict:
    "Payment succeeded, but this order is not pending — it has been left as it is. " +
    "Refund or re-place it deliberately.",
  mirrored: "Stripe has no completed payment for this order yet.",
  unknown: "Stripe has no record of this payment.",
};

export async function recheckPaymentAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };

  const id = Number(formData.get("order_id"));
  if (!id) return { error: "Nothing to check." };

  let outcome: string;
  try {
    ({ outcome } = await recheckOrderPayment(token, id));
  } catch (err) {
    if (err instanceof ApiError) {
      // 409 (no payment on this order) and 502 (Stripe unreachable) both carry a
      // message written for the vendor, so it is shown as written.
      return { error: err.message };
    }
    throw err;
  }

  // Revalidate whatever the outcome: even "nothing changed" may be news to a
  // page that has been open since before someone else advanced this order.
  revalidatePath(`/admin/orders/${id}`);
  revalidatePath("/admin/orders");
  return { ok: RECHECK_MESSAGE[outcome] ?? `Checked. Stripe says: ${outcome}.` };
}

/* ------------------------------------------------------------- catalog -- */

const text = (fd: FormData, key: string) => String(fd.get(key) ?? "").trim();

/** Everything the vendor edits is visible to shoppers, so a catalog write
 *  invalidates the storefront too -- not just the admin screen that made it. */
function revalidateCatalog(productId?: number, slug?: string) {
  revalidatePath("/admin/products");
  if (productId) revalidatePath(`/admin/products/${productId}`);
  revalidatePath("/", "layout");
  if (slug) revalidatePath(`/products/${slug}`);
}

/** Money arrives from a form as a string and must stay one. Number() then
 *  toString() would turn "24.10" into 24.1 and re-introduce float rounding on a
 *  numeric(10,2) column. */
function money(fd: FormData, key: string): string | null {
  const raw = text(fd, key);
  return raw === "" ? null : raw;
}

export async function createProductAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };

  let created;
  try {
    created = await createProduct(token, {
      name: text(formData, "name"),
      slug: text(formData, "slug"),
      description: text(formData, "description") || null,
      category_id: Number(formData.get("category_id")),
      base_price: money(formData, "base_price"),
      // The API requires at least one variant (Field(min_length=1)), so the
      // opening variant is part of creation rather than a follow-up step.
      variants: [
        {
          sku: text(formData, "sku"),
          variant_name: text(formData, "variant_name"),
          price_override: money(formData, "price_override"),
          quantity_available: Number(formData.get("quantity_available") ?? 0),
          reorder_level: Number(formData.get("reorder_level") ?? 0),
        },
      ],
    });
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }

  revalidateCatalog(created.id, created.slug);
  redirect(`/admin/products/${created.id}`);
}

export async function updateProductAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };
  const id = Number(formData.get("product_id"));

  try {
    const updated = await updateProduct(token, id, {
      name: text(formData, "name"),
      slug: text(formData, "slug"),
      description: text(formData, "description") || null,
      category_id: Number(formData.get("category_id")),
      base_price: money(formData, "base_price"),
    });
    revalidateCatalog(id, updated.slug);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }
  return { ok: "Product saved." };
}

export async function setProductActiveAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };
  const id = Number(formData.get("product_id"));
  // Deactivating is DELETE (the soft kind); reactivating is a PATCH, because
  // there is no "undelete" verb.
  const activate = formData.get("activate") === "true";

  try {
    if (activate) await updateProduct(token, id, { is_active: true });
    else await deactivateProduct(token, id);
    revalidateCatalog(id, text(formData, "slug"));
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }
  return { ok: activate ? "Product is visible again." : "Product hidden from the store." };
}

export async function addVariantAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };
  const id = Number(formData.get("product_id"));

  try {
    await addVariant(token, id, {
      sku: text(formData, "sku"),
      variant_name: text(formData, "variant_name"),
      price_override: money(formData, "price_override"),
      quantity_available: Number(formData.get("quantity_available") ?? 0),
      reorder_level: Number(formData.get("reorder_level") ?? 0),
    });
    revalidateCatalog(id, text(formData, "slug"));
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }
  return { ok: "Variant added." };
}

export async function updateVariantAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };

  try {
    await updateVariant(token, Number(formData.get("variant_id")), {
      sku: text(formData, "sku"),
      variant_name: text(formData, "variant_name"),
      price_override: money(formData, "price_override"),
    });
    revalidateCatalog(Number(formData.get("product_id")), text(formData, "slug"));
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }
  return { ok: "Variant saved." };
}

/** The picker sends one "key=value" pair, or "" for "shows on everything".
 *  Reassembled here rather than posted as JSON so the form stays a plain form
 *  and the admin never types a brace. */
function parseAppliesTo(raw: string): Record<string, string> {
  if (!raw) return {};
  const at = raw.indexOf("=");
  return at === -1 ? {} : { [raw.slice(0, at)]: raw.slice(at + 1) };
}

/** Step 1 of an upload: get a signed URL.
 *
 *  A server action rather than a client fetch because the admin's JWT lives in
 *  an httpOnly cookie the browser cannot read -- the same reason every other
 *  admin call goes through here. What comes back is safe to hand to the browser:
 *  it authorises one PUT, to one key, for fifteen minutes.
 *
 *  Takes plain arguments rather than FormData: it is called from an onChange
 *  handler, not a form submission. */
export async function requestUploadAction(
  filename: string,
  contentType: string,
  byteSize: number,
): Promise<{ key?: string; url?: string; headers?: Record<string, string>; error?: string }> {
  const { token, error } = await adminToken();
  if (!token) return { error };

  try {
    const target = await requestUpload(token, {
      filename,
      content_type: contentType,
      byte_size: byteSize,
    });
    return { key: target.key, url: target.url, headers: target.headers };
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }
}

/** Step 3: the PUT succeeded, so record it and get the public URL back. */
export async function confirmUploadAction(
  key: string,
  width: number | null,
  height: number | null,
): Promise<{ url?: string; assetId?: number; error?: string }> {
  const { token, error } = await adminToken();
  if (!token) return { error };

  try {
    const asset = await confirmUpload(token, { key, width, height });
    // The id travels with the url from here on. Without it the API cannot record
    // which asset an image came from, which is defect 24 -- the column existed
    // and the write path ignored it.
    return { url: asset.url, assetId: asset.id };
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }
}

export async function addImageAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };
  const id = Number(formData.get("product_id"));

  // An upload wins over a library pick. Both inputs are named separately rather
  // than sharing "url", because two fields with one name make FormData.get()
  // return whichever comes first in the DOM -- a rule about markup order, which
  // is not a rule anyone should have to know to move a fieldset.
  const uploaded = text(formData, "uploaded_url");
  const chosen = text(formData, "url");
  const url = uploaded || chosen;
  if (!url) {
    return { error: "Upload a photo, or choose one of the existing files." };
  }
  // Only ever set alongside `uploaded_url` -- a committed web/public/ file has
  // no asset behind it, and sending an id for one would be refused by the API's
  // match check anyway.
  const assetId = Number(text(formData, "uploaded_asset_id")) || null;

  try {
    await addProductImage(token, id, {
      url,
      asset_id: assetId,
      alt_text: text(formData, "alt_text"),
      is_primary: formData.get("is_primary") === "on",
      applies_to: parseAppliesTo(text(formData, "applies_to")),
    });
    revalidateCatalog(id, text(formData, "slug"));
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }
  return { ok: "Image added." };
}

export async function imageAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };
  const imageId = Number(formData.get("image_id"));
  const intent = formData.get("intent");
  const remove = intent === "delete";

  try {
    if (remove) await deleteProductImage(token, imageId);
    else if (intent === "applies")
      await updateProductImage(token, imageId, {
        applies_to: parseAppliesTo(text(formData, "applies_to")),
      });
    else await updateProductImage(token, imageId, { is_primary: true });
    revalidateCatalog(Number(formData.get("product_id")), text(formData, "slug"));
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }
  return {
    ok: remove
      ? "Image removed."
      : intent === "applies"
        ? "Image options updated."
        : "Primary image updated.",
  };
}

export async function updateInventoryAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };

  const variantId = Number(formData.get("variant_id"));
  const qty = Number(formData.get("quantity_available"));
  const reorder = Number(formData.get("reorder_level"));

  // Catch it here rather than shipping a request the API will 422. Both columns
  // also carry a >= 0 CHECK, so there are three layers and the database has the
  // last word.
  if (!Number.isInteger(qty) || qty < 0 || !Number.isInteger(reorder) || reorder < 0) {
    return { error: "Stock and reorder level must be whole numbers, zero or more." };
  }

  try {
    await updateInventory(token, variantId, {
      quantity_available: qty,
      reorder_level: reorder,
    });
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }

  revalidatePath("/admin/inventory");
  revalidatePath("/admin/products");
  // Stock decides "Sold out" on the storefront, so the shopper-facing pages are
  // stale the moment this changes.
  revalidatePath("/", "layout");
  const slug = text(formData, "slug");
  if (slug) revalidatePath(`/products/${slug}`);
  return { ok: "Saved." };
}

/* --------------------------------------------------------------- users -- */

function revalidateUser(id: number) {
  revalidatePath("/admin/users");
  revalidatePath(`/admin/users/${id}`);
  revalidatePath("/admin/audit");
}

/**
 * Suspend, reactivate, promote or demote.
 *
 * The specific change arrives as `intent` rather than raw field values, so the
 * form cannot express something meaningless like {is_active: null}. Which
 * intents are offered comes from the API's allowed_actions -- this never decides
 * for itself what is legal.
 */
export async function updateUserAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };

  const id = Number(formData.get("user_id"));
  const intent = String(formData.get("intent") ?? "");

  const body = {
    suspend: { is_active: false },
    reactivate: { is_active: true },
    promote: { role: "admin" },
    demote: { role: "customer" },
  }[intent];
  if (!body) return { error: "Unknown action." };

  try {
    await updateAdminUser(token, id, body);
  } catch (err) {
    // 409 here means a lockout guard fired -- suspending yourself, or demoting
    // the last admin. The API's sentence explains which; it is shown as written.
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }

  revalidateUser(id);
  return { ok: `Done: ${intent}.` };
}

export async function sendUserPasswordResetAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };
  const id = Number(formData.get("user_id"));

  try {
    const { detail } = await sendAdminPasswordReset(token, id);
    revalidateUser(id);
    return { ok: detail };
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }
}

export async function disableUserTwoFactorAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };
  const id = Number(formData.get("user_id"));

  try {
    await adminDisableTwoFactor(token, id);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }

  revalidateUser(id);
  return { ok: "Two-factor turned off. Tell them to set it up again." };
}

export async function anonymiseUserAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };

  const id = Number(formData.get("user_id"));
  const expected = String(formData.get("expected_email") ?? "");
  const typed = String(formData.get("confirm_email") ?? "").trim();

  // The API demands the admin's password. This second check is the UI's own:
  // an admin arrives here from a list of users, so the mistake worth preventing
  // is erasing the WRONG ROW, which a password prompt does nothing about.
  if (typed !== expected) {
    return { error: "The email you typed does not match this account." };
  }

  try {
    await adminAnonymise(token, id, String(formData.get("current_password") ?? ""));
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }

  revalidateUser(id);
  return { ok: "Account anonymised. Their orders are kept, without their details." };
}

/**
 * Record a dispatch: carrier, tracking number, and the order moves to shipped.
 *
 * Replaces the old "Mark shipped" button. That button set a status with nothing
 * behind it; PATCH now refuses `shipped` outright and names this path instead,
 * because a shipped order without a tracking number is precisely the row a
 * payment processor asks for during a "not received" dispute.
 */
export async function dispatchOrderAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };

  const id = Number(formData.get("order_id"));
  const carrier = String(formData.get("carrier") ?? "").trim();
  const tracking = String(formData.get("tracking_number") ?? "").trim();
  if (!id) return { error: "Nothing to dispatch." };

  // Checked here as well as by the API. Not duplication for its own sake: a
  // round trip to be told "you left the box empty" is a worse experience than
  // being told immediately, and the API still refuses regardless -- this is the
  // courtesy, that is the guard.
  if (!carrier) return { error: "Choose a carrier." };
  if (!tracking) return { error: "Enter the tracking number." };

  try {
    await dispatchOrder(token, id, { carrier, tracking_number: tracking });
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }

  revalidatePath(`/admin/orders/${id}`);
  revalidatePath("/admin/orders");
  return { ok: `Dispatched. Order #${id} is now shipped.` };
}

/**
 * Append an event to the parcel's history.
 *
 * `source` is submitted as `admin` because that is the truth: a human is
 * asserting this. There is no carrier webhook yet, and recording it as anything
 * else would launder an assertion into a confirmation.
 */
export async function recordShipmentEventAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };

  const id = Number(formData.get("order_id"));
  const status = String(formData.get("status") ?? "");
  if (!id || !status) return { error: "Nothing to record." };

  try {
    await recordShipmentEvent(token, id, { status, source: "admin" });
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }

  revalidatePath(`/admin/orders/${id}`);
  revalidatePath("/admin/orders");
  return { ok: `Recorded: ${status.replace(/_/g, " ")}.` };
}