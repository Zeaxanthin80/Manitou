import Image from "next/image";
import Link from "next/link";

import { buttonClasses } from "@/components/ui/button";
import { storeConfig } from "@/lib/store-config";

/**
 * The front page's opening: one full-bleed photograph, one panel of copy.
 *
 * **This deliberately overrides the "one big, quiet statement" direction** the
 * home page carried through Phase 3. That direction was a store name in 44px
 * Archivo Black over a tagline, and it made sense before there was a wordmark
 * in the header directly above it. Now it repeated the masthead, and a shop that
 * opens by saying its own name twice reads as a template. The photograph does
 * what the name was doing; the wordmark keeps the name.
 *
 * **Every word comes from `store-config.json`** (`home.featured`), for the same
 * reason `store.tagline` did: a clone must not edit a component to change its
 * pitch. The block already had an eyebrow, heading, body, button label and a
 * category slug for the featured-series band this replaces -- the hero is that
 * band promoted to lead, so the config shape did not change.
 *
 * **The panel sits on the photograph at every width, and it is translucent.**
 * The first version stacked it below the image on a phone and pulled it up by
 * 40px to "break the frame" -- and the frame won: the image wrapper is
 * `relative` and the panel's wasn't, so a positioned sibling painted over an
 * in-flow one and the overlap, eyebrow included, was hidden under the
 * photograph. Absolute at every width removes the bug and the trick together.
 * `bg-surface/80` with a backdrop blur keeps the copy legible over any part of
 * any photograph while still reading as one composition rather than a card
 * pasted on top; the tokens are unchanged, only their alpha.
 *
 * The frame is 3:4 on a phone -- taller than the 4:5 the tiles use -- so the
 * garments still show above a panel that covers roughly the lower 45%.
 *
 * The heading is the page's `<h1>`. The store name is carried by the wordmark's
 * alt text and by `<title>`; a heading that says what the store is *leading
 * with* is more useful to a reader and a crawler than one that repeats the tab.
 */
export function Hero() {
  // Widened from the generated `as const` literals, as the band did: the type
  // is regenerated from the JSON, so `category` types as its current value and
  // a literal-typed check would read as always-true.
  const featured: {
    category: string;
    eyebrow: string;
    heading: string;
    body: string;
    cta: string;
    image: string;
    image_alt: string;
  } = storeConfig.home.featured;

  // Empty category means "not leading with anything": no hero, and the page is
  // the plain catalogue. Same convention as `store.logo` -- the key stays, the
  // value empties -- so a clone switches it off without touching code.
  if (!featured.category) return null;

  return (
    <section aria-labelledby="hero-heading" className="relative">
      {/* Portrait on a phone, wide on a desktop. A 3:2 source composed with its
          subject in the upper right and empty backdrop lower left crops into
          both without covering the garments; the photograph is generated to
          that brief, and a future one that isn't gets a second art-directed
          <Image> rather than a change here. */}
      {/* The frame is bounded on BOTH axes, and the two bounds are the same
          number twice: max-h-[75svh] and max-w-[150svh]. That pins the worst
          case at exactly 2:1 whatever the window, because a box capped at H
          tall and 2H wide cannot be shaped otherwise.

          It matters because object-cover discards whatever the frame's shape
          does not want, and with only the HEIGHT capped the shape ran away. On
          a 1920px-wide window the box became 2.78:1 and threw away 45% of the
          photograph's height; a 1366x768 laptop did the same thing for the
          opposite reason, being short rather than wide. What the crop took was
          the empty backdrop the panel was composed to sit on, so the panel
          ended up over a garment and needed its blur to stay readable. Capping
          the width against the SAME viewport height holds the ratio at 2:1 and
          the loss at 23%, which is the crop that looked right in review.

          aspect-[20/13] is the photograph's own ratio, 2560x1664. It is the
          shape the frame relaxes to whenever there is room, so below about
          1400px nothing is cropped at all. A replacement photograph at a
          different ratio changes this one number and nothing else.

          svh, not vh: the height with browser chrome shown, so a phone's
          collapsing address bar cannot make the hero jump.

          w-full is load-bearing. With the width left auto, CSS transfers a
          max-height THROUGH an aspect ratio into a max-width, so the box keeps
          its ratio and shrinks sideways instead -- 682px tall, 1364px wide, and
          a bare strip of page down the right of a 1920px monitor. A definite
          width is what makes the height clamp and the ratio yield.

          The phone frame is unchanged and still crops the sides hard. A
          landscape photograph in a 3:4 portrait box has to lose width, and the
          box is 3:4 because the copy panel needs that height. The fix there is
          a second art-directed source, not a number here. */}
      <div className="relative mx-auto w-full aspect-[3/4] wide:aspect-[20/13] wide:max-h-[75svh] wide:max-w-[150svh]">
        <Image
          src={featured.image}
          alt={featured.image_alt}
          fill
          sizes="100vw"
          // The largest thing above the fold on the busiest page: the LCP
          // element. Worth the preload.
          priority
          className="object-cover"
        />
      </div>

      {/* Absolute at every width. On a phone the panel keeps the page's 24px
          gutter; above wide: the wrapper spans the section and the inner column
          is the same max-w-6xl the grid uses, so the panel's left edge lines up
          with everything below it. */}
      <div className="absolute inset-x-6 bottom-6 wide:inset-x-0 wide:bottom-10">
        <div className="mx-auto max-w-6xl wide:px-6">
          <div className="rounded-md border border-border/60 bg-surface/80 p-6 shadow-lg backdrop-blur-md wide:max-w-md wide:p-8">
            {/* Merchandising is what the accent token is for; this and the
                active nav item are its two appearances on the page. */}
            <p className="font-body text-xs uppercase tracking-wide text-accent">
              {featured.eyebrow}
            </p>
            <h1
              id="hero-heading"
              className="mt-3 font-display text-2xl uppercase leading-none tracking-tight text-text wide:text-3xl"
            >
              {featured.heading}
            </h1>
            <p className="mt-4 max-w-prose font-body text-sm text-muted wide:text-base">
              {featured.body}
            </p>
            <Link
              href={`/categories/${featured.category}`}
              className={buttonClasses({ className: "mt-6 inline-flex" })}
            >
              {featured.cta}
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
