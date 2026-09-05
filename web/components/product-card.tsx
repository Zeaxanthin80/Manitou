import Image from "next/image";
import Link from "next/link";

import type { ProductListItem } from "@/lib/api";
import { formatMoney, formatUnit } from "@/lib/format";

/**
 * Catalogue tile, Studio direction.
 *
 * Image and meta sit inside ONE bordered surface -- the card is the object, not
 * a picture with loose text under it.
 *
 * The price is set in the display face at text-lg and full contrast. In Studio
 * the price is the second most important thing on a tile after the photograph,
 * and Archivo Black is what gives it that weight; body-font muted text reads as
 * a caption.
 *
 * There is deliberately no variant line and no Add to cart here -- see the notes
 * on the catalogue page for why.
 */
export function ProductCard({ product }: { product: ProductListItem }) {
  return (
    <Link href={`/products/${product.slug}`} className="group block">
      {/* The tile answers a hover the way the references do: it lifts, its
          shadow deepens, and the photograph eases in by two percent. All three
          are transitions, all three are off under prefers-reduced-motion, and
          the image wrapper clips so the scaled photograph never leaks into the
          meta block beneath it. */}
      <article className="overflow-hidden rounded-md border border-border bg-surface transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-lg motion-reduce:transition-none motion-reduce:hover:translate-y-0">
        <div className="relative aspect-[4/5] overflow-hidden bg-background">
          {product.primary_image ? (
            <Image
              src={product.primary_image.url}
              // alt_text is NOT NULL in the schema precisely so this is never
              // empty by accident (Section 4.3's quality floor).
              alt={product.primary_image.alt_text}
              fill
              sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
              className="object-cover transition-transform group-hover:scale-[1.02] motion-reduce:transition-none"
            />
          ) : (
            <div className="flex h-full items-center justify-center font-body text-xs text-muted">
              No image
            </div>
          )}
        </div>

        <div className="p-4">
          <h2 className="font-display text-sm uppercase leading-tight tracking-tight text-text">
            {product.name}
          </h2>
          {/* "From" only when the variants genuinely differ. Showing it on a
              single-price product would imply a choice that does not exist. */}
          <p className="mt-2 font-display text-lg text-text">
            {product.min_price !== product.max_price && (
              <span className="font-body text-xs uppercase tracking-wide text-muted">
                From{" "}
              </span>
            )}
            {formatMoney(product.min_price)}
            <span className="font-body text-sm text-muted">
              {formatUnit(product.unit_of_measure)}
            </span>
          </p>
        </div>
      </article>
    </Link>
  );
}
