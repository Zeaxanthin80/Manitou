import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AddToCart } from "@/components/add-to-cart";
import { ApiError, getProduct } from "@/lib/api";
import { formatMoney, formatUnit } from "@/lib/format";
import { storeConfig } from "@/lib/store-config";

/**
 * Product detail, Studio direction.
 *
 * The accent earns its place here: "Sold out" is a real, consequential state,
 * which is exactly what "one sharp accent used sparingly" is for. It appears
 * nowhere else on this page.
 *
 * The variant picker and Add to cart live in <AddToCart>, a Client Component --
 * choosing a variant is browser state. The page around it stays a Server
 * Component, so the client boundary is drawn as tightly as the interaction
 * requires and no tighter.
 */
export default async function ProductPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  let product;
  try {
    product = await getProduct(slug);
  } catch (error) {
    // An inactive product 404s from the API by design -- hidden means hidden,
    // including by direct URL. That becomes a 404 page here, not a 500.
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const primary =
    product.images.find((i) => i.is_primary) ?? product.images[0] ?? null;
  const anyInStock = product.variants.some((v) => v.in_stock);

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <nav className="font-body text-xs uppercase tracking-tight text-muted">
        <Link href="/" className="hover:text-text">
          All products
        </Link>
        <span className="px-2">/</span>
        <Link
          href={`/categories/${product.category.slug}`}
          className="hover:text-text"
        >
          {product.category.name}
        </Link>
      </nav>

      <div className="mt-6 grid grid-cols-1 gap-12 md:grid-cols-2">
        <div className="relative aspect-[4/5] overflow-hidden rounded-md border border-border bg-surface">
          {primary ? (
            <Image
              src={primary.url}
              alt={primary.alt_text}
              fill
              sizes="(max-width: 768px) 100vw, 50vw"
              className="object-cover"
              priority
            />
          ) : (
            <div className="flex h-full items-center justify-center font-body text-sm text-muted">
              No image
            </div>
          )}
        </div>

        <div className="md:pt-2">
          <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
            {product.name}
          </h1>

          <p className="mt-4 font-body text-xl text-text">
            {formatMoney(product.base_price)}
            <span className="text-muted">{formatUnit(product.unit_of_measure)}</span>
          </p>

          {!anyInStock && (
            <p className="mt-3 inline-block rounded-sm bg-accent px-2 py-1 font-body text-xs uppercase tracking-tight text-surface">
              Sold out
            </p>
          )}

          {product.description && (
            <p className="mt-6 max-w-prose font-body text-base text-muted">
              {product.description}
            </p>
          )}

          {storeConfig.features.variants_enabled && (
            <AddToCart variants={product.variants} />
          )}
        </div>
      </div>
    </main>
  );
}
