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
