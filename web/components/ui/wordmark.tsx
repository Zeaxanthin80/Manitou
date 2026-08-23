import { storeConfig } from "@/lib/store-config";

/**
 * The store's name, as artwork if there is any and as live text otherwise.
 *
 * **Text is the default, not the degraded case.** `store.logo` is empty in the
 * committed config, so a clone gets a correctly styled wordmark by editing one
 * string in `store-config.json` -- no artwork, no image pipeline, nothing to
 * commission before the site looks finished. Setting `logo` swaps in a file.
 * Both paths are first-class, which is what keeps this a config seam rather than
 * a placeholder waiting to be replaced.
 *
 * **One component for all three call sites** -- storefront header, footer, admin
 * nav -- because the fallback rule has to be the same in each. Three copies of
 * `logo ? <img> : name` is three chances for one of them to keep rendering text
 * after the artwork lands, and a portal whose masthead disagrees with the
 * storefront's reads as two different sites.
 *
 * The span carries no typography of its own: every caller wraps this in an
 * element already styled `font-display text-lg uppercase tracking-tight`, and
 * inheritance means the fallback matches its surroundings without this file
 * knowing what those surroundings are. An <img> ignores those classes, which is
 * why the height lives here instead.
 */
export function Wordmark() {
  const { name, logo } = storeConfig.store;

  if (!logo) {
    return <span>{name}</span>;
  }

  return (
    /**
     * A plain <img>, not next/image, and the rule is silenced deliberately.
     *
     * next/image earns its keep by resizing and re-encoding photographs. It can
     * do neither to an SVG -- Next 16 forces `unoptimized` on any src ending
     * .svg -- so all that would remain of it here is its requirement for
     * explicit `width` and `height`. Those are numbers this file cannot know:
     * the artwork is named by config and can be swapped for a mark of a
     * different shape without touching code, and a hardcoded aspect ratio would
     * then silently squash it.
     *
     * Fixed height, intrinsic width: `h-5` is 20px against the 18px display
     * text it replaces, which is the usual optical match for a logo set beside
     * body copy. A mark up to roughly 6:1 sits comfortably in the header at that
     * height; anything wider needs the nav re-checked at 375px before shipping.
     */
    // eslint-disable-next-line @next/next/no-img-element
    <img src={logo} alt={name} className="h-5 w-auto" />
  );
}
