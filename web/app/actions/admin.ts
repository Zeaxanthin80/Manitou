"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  ApiError,
  addProductImage,
  addVariant,
  createProduct,
  deactivateProduct,
  deleteProductImage,
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

export async function addImageAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const { token, error } = await adminToken();
  if (!token) return { error };
  const id = Number(formData.get("product_id"));

  try {
    await addProductImage(token, id, {
      url: text(formData, "url"),
      alt_text: text(formData, "alt_text"),
      is_primary: formData.get("is_primary") === "on",
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
  const remove = formData.get("intent") === "delete";

  try {
    if (remove) await deleteProductImage(token, imageId);
    else await updateProductImage(token, imageId, { is_primary: true });
    revalidateCatalog(Number(formData.get("product_id")), text(formData, "slug"));
  } catch (err) {
    if (err instanceof ApiError) return { error: err.message };
    throw err;
  }
  return { ok: remove ? "Image removed." : "Primary image updated." };
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
