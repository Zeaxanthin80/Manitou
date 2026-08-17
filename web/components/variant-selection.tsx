"use client";

import { createContext, useContext, useState } from "react";

import type { Variant } from "@/lib/api";

/**
 * The selected variant, shared by the gallery and the picker.
 *
 * It used to live in AddToCart's own useState, which was fine while nothing else
 * cared. The gallery cares: picking "White" has to change the photograph, and
 * the two components sit on opposite sides of the page grid.
 *
 * A context provider rather than lifting everything into one big client
 * component, because the provider takes `children` — so the product name, price
 * and description stay server-rendered content passed down from the page, and
 * only the two interactive pieces ship as client components.
 *
 * Not the URL. Filters belong in the URL (the admin lists do exactly that), but
 * this is a picker: making a size change cost a server round-trip would be a
 * visible stutter on every click for no gain in shareability that matters.
 */

type Selection = {
  variant: Variant | null;
  select: (id: number) => void;
};

const Ctx = createContext<Selection | null>(null);

export function VariantSelectionProvider({
  variants,
  children,
}: {
  variants: Variant[];
  children: React.ReactNode;
}) {
  const sellable = variants.filter((v) => v.in_stock);
  // Preselect only when there is genuinely no choice to make. With several
  // options, choosing one for the customer risks them adding a size they never
  // picked -- the same reason the admin image picker preselects nothing.
  const [id, setId] = useState<number | null>(
    sellable.length === 1 ? sellable[0].id : null,
  );

  const variant = variants.find((v) => v.id === id) ?? null;

  return (
    <Ctx.Provider value={{ variant, select: setId }}>{children}</Ctx.Provider>
  );
}

/** Throws outside a provider rather than returning a silent null: a gallery that
 *  quietly stops reacting to the picker is the bug this whole change fixes. */
export function useVariantSelection(): Selection {
  const ctx = useContext(Ctx);
  if (!ctx) {
    throw new Error("useVariantSelection must be used inside VariantSelectionProvider");
  }
  return ctx;
}
