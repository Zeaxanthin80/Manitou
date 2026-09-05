import Link from "next/link";
import { redirect } from "next/navigation";

import { createProductAction } from "@/app/actions/admin";
import { ProductForm } from "@/components/product-form";
import { listCategories } from "@/lib/api";
import { getSession } from "@/lib/session";

export default async function NewProductPage() {
  const token = await getSession();
  if (!token) redirect("/login");

  // Public endpoint, no admin variant needed -- the category list is the same
  // one shoppers see, and reusing it avoids a second source of truth.
  const categories = await listCategories();

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <Link
        href="/admin/products"
        className="font-body text-xs uppercase tracking-wide text-muted hover:text-text"
      >
        &larr; All products
      </Link>
      <h1 className="mt-4 font-display text-2xl uppercase leading-none tracking-tight text-text">
        New product
      </h1>
      <p className="mt-3 max-w-prose font-body text-sm text-muted">
        Images and further variants can be added once the product exists.
      </p>

      {/* The dead end that WAS defect 23, now a signpost.
          `products.category_id` is NOT NULL, so with no categories this form
          cannot be submitted no matter what is typed into it. Rendering it
          anyway produced the original report: an empty Category dropdown, a
          mandatory field, and nothing on the page explaining what to do.
          Building /admin/categories without fixing this would leave the same
          dead end for anyone who did not already know that page existed. */}
      {categories.length === 0 ? (
        <div className="mt-8 max-w-prose rounded-md border border-border bg-surface p-6">
          <h2 className="font-body text-sm uppercase tracking-tight text-text">
            Add a category first
          </h2>
          <p className="mt-3 font-body text-sm text-muted">
            Every product belongs to a category, and this store has none yet — so
            there is nothing to file a product under. Creating one takes a name
            and nothing else.
          </p>
          <Link
            href="/admin/categories"
            className="mt-4 inline-block font-body text-sm text-text underline underline-offset-4 hover:text-accent"
          >
            Go to categories
          </Link>
        </div>
      ) : (
        <div className="mt-8">
          <ProductForm
            action={createProductAction}
            categories={categories}
            submitLabel="Create product"
          />
        </div>
      )}
    </main>
  );
}
