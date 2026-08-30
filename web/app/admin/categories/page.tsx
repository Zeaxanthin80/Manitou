import { notFound, redirect } from "next/navigation";

import { CategoriesEditor } from "@/components/categories-editor";
import { ApiError, listAdminCategories } from "@/lib/api";
import { getSession } from "@/lib/session";

/**
 * Category management.
 *
 * **This page is the store's bootstrap.** `products.category_id` is NOT NULL, so
 * until a category exists no product can be created — and before this page
 * existed, categories only ever came from `seed.py`, which correctly refuses to
 * run anywhere but a local machine. A production database built by migrations
 * alone had no way to get a first product at all. That was defect 23, and it was
 * invisible for five phases because every database anyone developed against had
 * been seeded.
 *
 * Uses the admin endpoint rather than the public `GET /categories`, and the
 * difference is the two counts: how many products and subcategories each holds.
 * The storefront has no use for those; this screen cannot explain why a category
 * refuses to be deleted without them.
 *
 * Not paginated, unlike products, orders and users — a hand-maintained category
 * tree is tens of rows, and rendering it as a tree needs all of them at once to
 * place children under parents.
 */
export default async function AdminCategoriesPage() {
  const token = await getSession();
  if (!token) redirect("/login");

  let categories;
  try {
    categories = await listAdminCategories(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && error.status === 403) notFound();
    throw error;
  }

  return (
    <div className="mt-10 flex flex-col gap-14">
      <div>
        <h1 className="font-display text-2xl text-text">Categories</h1>
        <p className="mt-2 max-w-2xl font-body text-sm text-muted">
          Every product belongs to a category, and the storefront navigates by
          them. A category can only be removed once nothing is inside it.
        </p>
      </div>

      <CategoriesEditor categories={categories} />
    </div>
  );
}
