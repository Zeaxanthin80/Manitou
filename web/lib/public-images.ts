import { readdir } from "node:fs/promises";
import path from "node:path";

/**
 * The images actually sitting in web/public/, for the admin image picker.
 *
 * Server-only: it reads this app's own filesystem. It lives on the web side
 * rather than behind an API endpoint because public/ belongs to the Next app --
 * the API is a separate service and in production a separate container, so it
 * has no view of this directory at all.
 *
 * Why a picker instead of a text field: a free-text URL let an external address
 * reach the database, and next/image then threw at RENDER time for every
 * visitor, taking out the home page, the product page and the admin edit page
 * together -- the last of which is the only screen that can remove the image.
 * Offering a list of real files makes the whole class of mistake unavailable.
 * The API-side validator stays regardless; this is the UI half, not a
 * replacement for it.
 *
 * Phase 6 moves storage to S3 + CloudFront and this becomes a real upload. The
 * shape the API receives -- a url string -- does not change, which is why this
 * is not throwaway work.
 */

/**
 * Raster formats only. next/image refuses to optimise SVG unless
 * `dangerouslyAllowSVG` is set, so offering the .svg files Next ships in
 * public/ would list options that render broken. They are template assets, not
 * product photography, so nothing is lost.
 */
const RENDERABLE = /\.(png|jpe?g|webp|avif|gif)$/i;

export async function listPublicImages(): Promise<string[]> {
  try {
    const dir = path.join(process.cwd(), "public");
    const entries = await readdir(dir, { withFileTypes: true });
    return entries
      .filter((e) => e.isFile() && RENDERABLE.test(e.name))
      .map((e) => `/${e.name}`)
      .sort();
  } catch {
    // A missing or unreadable public/ is not worth crashing the edit page for.
    // The picker renders its empty state and the page still works.
    return [];
  }
}
