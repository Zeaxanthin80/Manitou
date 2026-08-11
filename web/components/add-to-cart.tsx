"use client";

import { useActionState, useState } from "react";

import { addToCartAction } from "@/app/actions/cart";
import { Button } from "@/components/ui/button";
import type { Variant } from "@/lib/api";
import { formatMoney } from "@/lib/format";

/**
 * Variant picker plus Add to cart.
 *
 * The picker is what makes "Add to cart" meaningful on a multi-variant product:
 * you cannot ship "a t-shirt", only a Small Black one. That is the same reason
 * cart_items references product_variants rather than products.
 *
 * When there is exactly one variant -- the single-item shape from seed.py, one
 * default variant with empty attributes -- no picker renders at all. Offering a
 * choice of one is noise.
 */
export function AddToCart({ variants }: { variants: Variant[] }) {
  const sellable = variants.filter((v) => v.in_stock);
  const [selected, setSelected] = useState<number | null>(
    sellable.length === 1 ? sellable[0].id : null,
  );
  const [state, formAction, pending] = useActionState(addToCartAction, {});

  if (variants.length === 0) return null;

  const single = variants.length === 1;
  const soldOut = sellable.length === 0;

  return (
    <form action={formAction} className="mt-8 flex flex-col gap-4">
      <input type="hidden" name="variant_id" value={selected ?? ""} />
      <input type="hidden" name="quantity" value={1} />

      {!single && (
        <fieldset className="flex flex-col gap-2">
          {/* A fieldset/legend pair is what tells a screen reader these radios
              are one group and what the group is for. */}
          <legend className="mb-2 font-body text-xs uppercase tracking-tight text-muted">
            Options
          </legend>
          {variants.map((v) => (
            <label
              key={v.id}
              className={
                v.in_stock
                  ? "flex cursor-pointer items-baseline justify-between border-b border-border py-3 font-body text-sm has-checked:border-text"
                  : "flex items-baseline justify-between border-b border-border py-3 font-body text-sm opacity-50"
              }
            >
              <span className="flex items-center gap-3">
                <input
                  type="radio"
                  name="variant_choice"
                  value={v.id}
                  disabled={!v.in_stock}
                  checked={selected === v.id}
                  onChange={() => setSelected(v.id)}
                  className="accent-text"
                />
                <span className={v.in_stock ? "text-text" : "text-muted line-through"}>
                  {v.variant_name}
                </span>
              </span>
              <span className="flex items-baseline gap-4">
                <span className="text-text">{formatMoney(v.price)}</span>
                {!v.in_stock && (
                  <span className="text-xs uppercase tracking-tight text-accent">
                    Sold out
                  </span>
                )}
              </span>
            </label>
          ))}
        </fieldset>
      )}

      {state.error && (
        <p role="alert" className="font-body text-sm text-error">
          {state.error}
        </p>
      )}

      <Button
        type="submit"
        size="lg"
        disabled={pending || soldOut || selected === null}
      >
        {soldOut
          ? "Sold out"
          : pending
            ? "Adding..."
            : selected === null
              ? "Select an option"
              : "Add to cart"}
      </Button>
    </form>
  );
}
