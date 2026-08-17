import type { Image, Variant } from "@/lib/api";

/**
 * Which images belong to which variant — the browser half of the same rule the
 * API keeps in backend/app/services/image_match.py.
 *
 * Duplicated across two languages, deliberately and reluctantly. The API cannot
 * do this filtering for us: the customer changes variant without a request, so
 * the decision has to be made client-side from data already on the page. Kept to
 * one tiny function on each side so the two can be read against each other in
 * full, and pinned by tests on the API side.
 */

/**
 * A SUBSET test, not equality. `{color: "Black"}` matches a variant whose
 * attributes are `{size: "L", color: "Black"}`, because a photograph of a black
 * shirt is a photograph of every size of black shirt.
 *
 * Every pair must match, not any: `{color: "Black", fit: "Slim"}` is a photo of
 * a slim black shirt and must not appear on a regular black one.
 *
 * An empty tag matches everything, which is what `.every()` over an empty list
 * returns — the wanted behaviour, not an accident.
 */
export function matches(
  appliesTo: Record<string, string>,
  attributes: Record<string, string>,
): boolean {
  return Object.entries(appliesTo).every(([k, v]) => attributes[k] === v);
}

/**
 * The images to show for the current selection, in their existing order.
 *
 * `variant` is null when nothing is picked yet — a multi-variant product the
 * customer has not chosen from. Everything shows then: filtering to a variant
 * nobody selected would hide photographs for no reason.
 */
export function visibleFor(images: Image[], variant: Variant | null): Image[] {
  if (!variant) return images;

  const shown = images.filter((img) =>
    matches(img.applies_to ?? {}, variant.attributes),
  );

  // Images tagged FOR this variant lead; untagged ones follow.
  //
  // Without this the gallery filters correctly and still opens on the wrong
  // picture: an untagged primary matches every variant and sorts first, so
  // choosing White leaves a generic shot on screen and buries the white one in
  // the strip. Filtering was never the goal -- showing the thing they picked is.
  //
  // A stable partition, so relative order inside each group is untouched.
  const specific = shown.filter((i) => Object.keys(i.applies_to ?? {}).length > 0);
  const generic = shown.filter((i) => Object.keys(i.applies_to ?? {}).length === 0);
  return [...specific, ...generic];
}
