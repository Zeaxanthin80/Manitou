import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Combine class names, resolving Tailwind conflicts.
 *
 * clsx handles the conditional logic; twMerge handles the part that actually
 * matters: when a caller passes `p-8` and the component already has `p-4`, both
 * classes would otherwise survive at equal CSS specificity and stylesheet source
 * order would decide the winner -- arbitrarily, and differently as the app
 * grows. twMerge understands Tailwind's grammar and drops the earlier one.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
