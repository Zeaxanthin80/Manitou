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
        className="font-body text-xs uppercase tracking-tight text-muted hover:text-text"
      >
        &larr; All products
      </Link>
      <h1 className="mt-4 font-display text-2xl uppercase leading-none tracking-tight text-text">
        New product
      </h1>
      <p className="mt-3 max-w-prose font-body text-sm text-muted">
        Images and further variants can be added once the product exists.
      </p>

      <div className="mt-8">
        <ProductForm
          action={createProductAction}
          categories={categories}
          submitLabel="Create product"
        />
      </div>
    </main>
  );
}
