"use client";

import { useActionState, useState } from "react";

import { placeOrderAction } from "@/app/actions/checkout";
import { Button } from "@/components/ui/button";
import type { Address } from "@/lib/api";

function describe(a: Address) {
  return [a.line1, a.line2, a.city, a.state, a.postal_code, a.country]
    .filter(Boolean)
    .join(", ");
}

function AddressChoice({
  name,
  addresses,
  selected,
  onSelect,
  legend,
}: {
  name: string;
  addresses: Address[];
  selected: number | null;
  onSelect: (id: number) => void;
  legend: string;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-2 font-body text-xs uppercase tracking-wide text-muted">
        {legend}
      </legend>
      {addresses.map((a) => (
        <label
          key={a.id}
          className="flex cursor-pointer items-start gap-3 border-b border-border py-3 font-body text-sm has-checked:border-text"
        >
          <input
            type="radio"
            name={name}
            value={a.id}
            checked={selected === a.id}
            onChange={() => onSelect(a.id)}
            className="mt-1 accent-text"
          />
          <span className="text-text">{describe(a)}</span>
        </label>
      ))}
    </fieldset>
  );
}

/**
 * Address selection and Place order.
 *
 * Client-side because choosing a radio and toggling "same as shipping" is
 * browser state. The consequential work -- reading the cart, pricing it, moving
 * stock -- all happens on the server; nothing here is trusted.
 *
 * The two address ids are submitted as hidden inputs rather than by relying on
 * the radios' own names, so that when "same as shipping" is checked the billing
 * field carries a real value instead of being absent and silently defaulting.
 */
export function CheckoutForm({ addresses }: { addresses: Address[] }) {
  const defaultShipping =
    addresses.find((a) => a.is_default && a.type === "shipping") ??
    addresses.find((a) => a.type === "shipping") ??
    addresses[0];

  const [shipping, setShipping] = useState<number | null>(
    defaultShipping?.id ?? null,
  );
  const [sameAsShipping, setSameAsShipping] = useState(true);
  const [billing, setBilling] = useState<number | null>(
    defaultShipping?.id ?? null,
  );
  const [state, formAction, pending] = useActionState(placeOrderAction, {});

  const effectiveBilling = sameAsShipping ? shipping : billing;

  return (
    <form action={formAction} className="flex flex-col gap-8">
      <input type="hidden" name="shipping_address_id" value={shipping ?? ""} />
      <input
        type="hidden"
        name="billing_address_id"
        value={effectiveBilling ?? ""}
      />

      <AddressChoice
        name="shipping_choice"
        legend="Deliver to"
        addresses={addresses}
        selected={shipping}
        onSelect={setShipping}
      />

      <div>
        <label className="flex cursor-pointer items-center gap-3 font-body text-sm text-text">
          <input
            type="checkbox"
            checked={sameAsShipping}
            onChange={(e) => setSameAsShipping(e.target.checked)}
            className="accent-text"
          />
          Billing address same as delivery
        </label>

        {!sameAsShipping && (
          <div className="mt-4">
            <AddressChoice
              name="billing_choice"
              legend="Bill to"
              addresses={addresses}
              selected={billing}
              onSelect={setBilling}
            />
          </div>
        )}
      </div>

      {state.error && (
        <p role="alert" className="font-body text-sm text-error">
          {state.error}
        </p>
      )}

      <Button
        type="submit"
        size="lg"
        disabled={pending || shipping === null || effectiveBilling === null}
      >
        {pending ? "Placing order..." : "Continue to payment"}
      </Button>

      <p className="font-body text-xs text-muted">
        You will enter card details on the next step.
      </p>
    </form>
  );
}
