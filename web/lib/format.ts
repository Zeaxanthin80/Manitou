import { storeConfig } from "@/lib/store-config";

/**
 * Format a money string for display.
 *
 * Currency and locale come from store-config.json -- a cloned store changes one
 * file and every price on the site follows. Nothing here hardcodes a "$".
 *
 * The input is the string the API sent ("24.00"). Number() is used only at the
 * final display step; no arithmetic is ever done on money in the browser,
 * because the API is the single place totals are calculated.
 */
export function formatMoney(amount: string): string {
  return new Intl.NumberFormat(storeConfig.locale, {
    style: "currency",
    currency: storeConfig.currency.code,
  }).format(Number(amount));
}

/** "each" needs no suffix; a weight unit does -- the Section 1.1 grocery seam. */
export function formatUnit(unit: string): string {
  return unit === "each" ? "" : ` / ${unit}`;
}

/**
 * An address as you would write it on a parcel, one line per line.
 *
 * Exists because the shipping address is retyped into a carrier's own site to
 * buy postage -- Manitou never prints a carrier label, since a valid one needs
 * paid postage and a barcode in the carrier's symbology. So the useful thing
 * this app can do is hand over the address in a form that pastes cleanly.
 *
 * The recipient comes from the ORDER's customer rather than the address row:
 * `addresses` has no name column, because an address belongs to a user and the
 * user carries the name.
 *
 * Blank parts are dropped rather than left as empty lines -- `line2` is usually
 * absent, and a carrier form pasted with a gap in the middle is a support call.
 */
export function postalAddress(
  recipient: string,
  address: {
    line1: string;
    line2?: string | null;
    city: string;
    state?: string | null;
    postal_code: string;
    country: string;
  },
): string {
  // "Miami, FL 33135", not "Miami, FL, 33135". The comma separates place from
  // region; the postal code follows on a space. This is the form a carrier's
  // site expects, and this string exists to be pasted into one -- which is also
  // why it differs from AddressBlock on screen, where the display simply joins
  // the parts.
  //
  // It degrades correctly outside the US: with no state, "London NW1 6XE".
  const locality = [address.city, address.state].filter(Boolean).join(", ");
  const localityLine = [locality, address.postal_code]
    .filter((part) => part && part.trim())
    .join(" ");

  return [recipient, address.line1, address.line2, localityLine, address.country]
    .filter((line) => line && line.trim())
    .join("\n");
}
