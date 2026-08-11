import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { updateProductAction } from "@/app/actions/admin";
import { ProductForm } from "@/components/product-form";
import { ProductImagesEditor } from "@/components/product-images-editor";
import { ProductVariantsEditor } from "@/components/product-variants-editor";
import { ProductVisibility } from "@/components/product-visibility";
import { ApiError, listAdminProducts, listCategories } from "@/lib/api";
import { getSession } from "@/lib/session";

/**
 * Edit one product: its own fields, its variants, its images, its visibility.
 *
 * There is no GET /admin/products/{id} -- the list endpoint already returns
 * everything this page needs, so it filters rather than adding an endpoint that
 * would duplicate _to_product. If the catalog outgrows one page of results, that
 * trade flips and the endpoint should be added.
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

  let products, categories;
  try {
    [products, categories] = await Promise.all([
      listAdminProducts(token),
      listCategories(),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && error.status === 403) notFound();
    throw error;
  }

  const product = products.items.find((p) => p.id === productId);
  if (!product) notFound();

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <Link
        href="/admin/products"
        className="font-body text-xs uppercase tracking-tight text-muted hover:text-text"
      >
        &larr; All products
      </Link>

      <div className="mt-4 flex flex-wrap items-center gap-4">
        <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
          {product.name}
        </h1>
        {!product.is_active && (
          <span className="rounded-sm border border-accent px-2 py-1 font-body text-xs uppercase tracking-tight text-accent">
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
        <ProductImagesEditor product={product} />

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
