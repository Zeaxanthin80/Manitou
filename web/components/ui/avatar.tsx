/**
 * A single initial in a circle.
 *
 * Not a photo: there is no avatar column in the schema, and adding one to make a
 * header prettier would be inventing a feature. This renders what we actually
 * have.
 *
 * Shared by the storefront and the portal so the signed-in marker is the same
 * object in both halves of the product.
 *
 * **One character, not two, and that is a correctness decision rather than a
 * visual one.** The previous version took the first letter of the first word
 * plus the first letter of the LAST word -- which quietly asserts that the last
 * word is the family name. That is the same assumption `users.full_name` exists
 * as one column to avoid:
 *
 *   José García Márquez  ->  "JM"  took the maternal surname, dropped the
 *                                  paternal one, which is the primary in
 *                                  Spanish convention
 *   Wang Xiaoming        ->  "WX"  family name comes first here, so this
 *                                  reverses the intent
 *
 * Two initials exist to tell people apart in a list -- Slack members, document
 * collaborators. This avatar renders in exactly two places, the storefront
 * account menu and the admin nav, and both show the SIGNED-IN USER'S OWN
 * account. It never appears beside anybody else's, and the full name sits
 * directly beneath it in the dropdown. There is nothing to disambiguate, so the
 * only thing the second character bought was the assumption.
 */

/**
 * The first character a reader would point at.
 *
 * Not `value[0]`, which indexes UTF-16 code UNITS: a name beginning with an
 * astral character returns half a surrogate pair and renders as a replacement
 * box. With two initials a broken one was half the label; with one it is the
 * whole thing.
 */
function firstCharacter(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";

  // Segmenter groups a base letter with its combining marks, so "É" written as
  // E + U+0301 stays "É" instead of decaying to a bare "E". That is not an edge
  // case for this store -- José, Ángela and Íñigo are ordinary customer names.
  if (typeof Intl !== "undefined" && "Segmenter" in Intl) {
    const [first] = new Intl.Segmenter(undefined, {
      granularity: "grapheme",
    }).segment(trimmed);
    if (first) return first.segment;
  }

  // Array.from iterates code POINTS, so an astral character survives whole.
  // Reached only on a runtime without Segmenter, where a decomposed accent
  // degrades to its base letter -- wrong, but legible, unlike a broken glyph.
  return Array.from(trimmed)[0] ?? "";
}

export function initial(fullName: string, email: string): string {
  // The email always exists, so a customer who left the name blank still gets a
  // marker rather than an empty circle.
  return (firstCharacter(fullName) || firstCharacter(email)).toUpperCase();
}

export const avatarClass =
  "flex size-9 items-center justify-center rounded-full bg-primary font-body text-xs text-surface transition-colors hover:bg-text motion-reduce:transition-none";
