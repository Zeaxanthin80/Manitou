/**
 * Initials in a circle.
 *
 * Not a photo: there is no avatar column in the schema, and adding one to make a
 * header prettier would be inventing a feature. This renders what we actually
 * have.
 *
 * Shared by the storefront and the portal so the signed-in marker is the same
 * object in both halves of the product.
 */
export function initials(fullName: string, email: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  // A blank name still needs a marker, and the email always exists.
  return email.slice(0, 2).toUpperCase();
}

export const avatarClass =
  "flex size-9 items-center justify-center rounded-full bg-primary font-body text-xs text-surface transition-colors hover:bg-text motion-reduce:transition-none";
