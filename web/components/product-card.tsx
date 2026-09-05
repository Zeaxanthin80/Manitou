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
      {/* The tile answers a hover the way the references do: it lifts, a
          shadow appears, and the photograph eases in by two percent.

          Three things make it smooth rather than jittery, and each was learned
          the hard way on the first version:

          - The hover is the LINK's (`group-hover:`), not the article's. The
            article is what moves; if it were also the hover target, the
            pointer at its bottom edge would leave the lifted box, the card
            would drop, the pointer would re-enter, and it would lift again --
            a two-pixel flicker loop. The link's box never moves.
          - The shadow is a pseudo-element that fades in. Animating box-shadow
            itself repaints on every frame; opacity is composited.
          - 300ms ease-out, not the 150ms default, so the lift reads as
            settling rather than snapping.

          The article no longer clips (a clipped shadow is no shadow); the
          image wrapper clips instead, with the top corners rounded to match.
          All of it is off under prefers-reduced-motion. */}
      <article className="relative rounded-md border border-border bg-surface transition-transform duration-300 ease-out will-change-transform group-hover:-translate-y-0.5 motion-reduce:transition-none motion-reduce:group-hover:translate-y-0 after:pointer-events-none after:absolute after:inset-0 after:rounded-md after:opacity-0 after:shadow-lg after:transition-opacity after:duration-300 group-hover:after:opacity-100 motion-reduce:after:transition-none">
        <div className="relative aspect-[4/5] overflow-hidden rounded-t-md bg-background">
          {product.primary_image ? (
            <Image
              src={product.primary_image.url}
              // alt_text is NOT NULL in the schema precisely so this is never
              // empty by accident (Section 4.3's quality floor).
              alt={product.primary_image.alt_text}
              fill
              sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
              className="object-cover transition-transform duration-300 ease-out will-change-transform group-hover:scale-[1.02] motion-reduce:transition-none"
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
