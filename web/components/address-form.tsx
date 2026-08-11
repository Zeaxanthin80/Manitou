"use client";

import { useActionState } from "react";

import { addAddressAction } from "@/app/actions/checkout";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";

/**
 * Add a delivery address during checkout.
 *
 * This lives here rather than only on an account page because a customer who
 * registered five minutes ago has no addresses at all, and orders.shipping_address_id
 * is NOT NULL -- without this form their checkout is a dead end.
 *
 * `required` is set on the fields the API requires (Field(min_length=1)); state
 * and line2 are optional in both places. The browser check is a convenience, not
 * the guard -- Pydantic still validates every field at the boundary.
 */
export function AddressForm({ compact = false }: { compact?: boolean }) {
  const [state, formAction, pending] = useActionState(addAddressAction, {});

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <FormField id="line1" label="Address" required>
        {(control) => <Input {...control} name="line1" autoComplete="address-line1" />}
      </FormField>

      <FormField id="line2" label="Apartment, suite, etc.">
        {(control) => <Input {...control} name="line2" autoComplete="address-line2" />}
      </FormField>

      <div className={compact ? "flex flex-col gap-4" : "grid gap-4 sm:grid-cols-2"}>
        <FormField id="city" label="City" required>
          {(control) => (
            <Input {...control} name="city" autoComplete="address-level2" />
          )}
        </FormField>
        <FormField id="state" label="State / Province">
          {(control) => (
            <Input {...control} name="state" autoComplete="address-level1" />
          )}
        </FormField>
        <FormField id="postal_code" label="Postal code" required>
          {(control) => (
            <Input {...control} name="postal_code" autoComplete="postal-code" />
          )}
        </FormField>
        <FormField id="country" label="Country" required hint="Two-letter code, e.g. US">
          {(control) => (
            <Input
              {...control}
              name="country"
              autoComplete="country"
              defaultValue="US"
            />
          )}
        </FormField>
      </div>

      {state.error && (
        <p role="alert" className="font-body text-sm text-error">
          {state.error}
        </p>
      )}

      <Button type="submit" variant="ghost" disabled={pending}>
        {pending ? "Saving..." : "Save address"}
      </Button>
    </form>
  );
}
