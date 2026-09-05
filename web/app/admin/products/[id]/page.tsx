import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { updateProductAction } from "@/app/actions/admin";
import { ProductForm } from "@/components/product-form";
import { ProductImagesEditor } from "@/components/product-images-editor";
import { ProductVariantsEditor } from "@/components/product-variants-editor";
import { ProductVisibility } from "@/components/product-visibility";
import { ApiError, getAdminProduct, listCategories } from "@/lib/api";
import { listPublicImages } from "@/lib/public-images";
import { getSession } from "@/lib/session";

/**
 * Edit one product: its own fields, its variants, its images, its visibility.
 *
 * Reads GET /admin/products/{id}. It used to fetch the whole list and pick the
 * product out with .find(), which is the trade this comment used to describe as
 * acceptable "until the catalog outgrows one page of results". It did not need to
 * outgrow anything: the list is paged at 50, so product 51 came back as a 404
 * indistinguishable from a deleted one, and adding sorting made WHICH products
 * were reachable depend on how the list was last sorted.
 */
export default async function EditProductPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const token = await getSession();
  if (!token) redirect("/login");

  const { id } = await params;
  const productId = Number(id);
  if (!Number.isInteger(productId)) notFound();

  // available is a local filesystem read, so it cannot fail the way the two API
  // calls can -- listPublicImages swallows its own errors and returns [].
  const available = await listPublicImages();

  let product, categories;
  try {
    [product, categories] = await Promise.all([
      getAdminProduct(token, productId),
      listCategories(),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    // 403 and 404 both land on the not-found page: a non-admin must not be able
    // to tell a product that exists from one that does not.
    if (error instanceof ApiError && [403, 404].includes(error.status)) notFound();
    throw error;
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <Link
        href="/admin/products"
        className="font-body text-xs uppercase tracking-wide text-muted hover:text-text"
      >
        &larr; All products
      </Link>

      <div className="mt-4 flex flex-wrap items-center gap-4">
        <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
          {product.name}
        </h1>
        {!product.is_active && (
          <span className="rounded-sm border border-accent px-2 py-1 font-body text-xs uppercase tracking-wide text-accent">
            Hidden
          </span>
        )}
        <Link
          href={`/products/${product.slug}`}
          className="ml-auto font-body text-sm text-muted underline hover:text-text"
        >
          View on storefront
        </Link>
      </div>

      <div className="mt-10 flex flex-col gap-14">
        <section>
          <h2 className="mb-4 font-body text-sm uppercase tracking-tight text-muted">
            Details
          </h2>
          <ProductForm
            action={updateProductAction}
            categories={categories}
            product={product}
            submitLabel="Save changes"
          />
        </section>

        <ProductVariantsEditor product={product} />
        <ProductImagesEditor product={product} available={available} />

        <section>
          <h2 className="mb-4 font-body text-sm uppercase tracking-tight text-muted">
            Visibility
          </h2>
          <ProductVisibility
            productId={product.id}
            slug={product.slug}
            isActive={product.is_active}
          />
        </section>
      </div>
    </main>
  );
}
