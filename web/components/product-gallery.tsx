"use client";

import Image from "next/image";
import { useRef, useState } from "react";

import { useVariantSelection } from "@/components/variant-selection";
import type { Image as ProductImage } from "@/lib/api";
import { cn } from "@/lib/cn";
import { visibleFor } from "@/lib/image-match";

/**
 * Main image plus a thumbnail strip.
 *
 * Exists because every image after the first was invisible: the product page
 * picked the primary and discarded the rest, so adding a second image in the
 * portal changed nothing a customer could see.
 *
 * Takes every image and filters to the selected variant itself, so the page can
 * stay a Server Component and hand it the raw list.
 */
export function ProductGallery({ images: all }: { images: ProductImage[] }) {
  const { variant } = useVariantSelection();
  const images = visibleFor(all, variant);
  const strip = useRef<HTMLDivElement>(null);

  // The chosen image is tracked by URL, not by index.
  //
  // Picking a different option replaces the list, and an index into the old list
  // means nothing in the new one -- it can point past the end and render blank.
  // The first version synced an index with an effect, which both tripped
  // react-hooks/set-state-in-effect and was the wrong shape: this is derived
  // state, not state that needs syncing.
  //
  // Falling back to images[0] when the chosen URL is no longer visible gives the
  // reset for free, and keeps the customer on the same photograph when it
  // survives the filter -- which an index reset would have thrown away.
  const [chosen, setChosen] = useState<string | null>(null);
  const active = Math.max(
    0,
    images.findIndex((i) => i.url === chosen),
  );

  if (images.length === 0) {
    return (
      <div className="relative aspect-[4/5] overflow-hidden rounded-md border border-border bg-surface">
        <div className="flex h-full items-center justify-center font-body text-sm text-muted">
          No image
        </div>
      </div>
    );
  }

  const current = images[active];

  /** Left/Right move along the strip, the way a radio group does. Without this
   *  a keyboard user tabs through every thumbnail to reach the last one. */
  const onKeyDown = (e: React.KeyboardEvent) => {
    const delta = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    e.preventDefault();
    const next = (active + delta + images.length) % images.length;
    setChosen(images[next].url);
    // Move focus with the selection, or the ring is left behind on a thumbnail
    // that is no longer the active one.
    strip.current
      ?.querySelectorAll<HTMLButtonElement>("button")
      [next]?.focus();
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="relative aspect-[4/5] overflow-hidden rounded-md border border-border bg-surface">
        <Image
          src={current.url}
          alt={current.alt_text}
          fill
          sizes="(max-width: 768px) 100vw, 50vw"
          className="object-cover"
          // Only the first image of the first render is the LCP element.
          // Marking every image priority tells the browser nothing is urgent.
          priority={active === 0}
        />
      </div>

      {/* One image needs no chooser. Rendering a strip of one is noise, and it
          is what this page showed before the gallery existed. */}
      {images.length > 1 && (
        <div
          ref={strip}
          role="group"
          aria-label="Product images"
          onKeyDown={onKeyDown}
          className="grid grid-cols-5 gap-2"
        >
          {images.map((img, i) => (
            <button
              key={img.url}
              type="button"
              onClick={() => setChosen(img.url)}
              aria-label={`Show image ${i + 1} of ${images.length}`}
              aria-current={i === active ? "true" : undefined}
              className={cn(
                "relative aspect-square overflow-hidden rounded-sm border bg-surface",
                "transition-colors motion-reduce:transition-none",
                i === active
                  ? "border-accent"
                  : "border-border hover:border-muted",
              )}
            >
              <Image
                src={img.url}
                // The main image carries the description. Repeating it on every
                // thumbnail makes a screen reader read the same sentence five
                // times; the button's own label says which one this is.
                alt=""
                fill
                sizes="96px"
                className="object-cover"
              />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
