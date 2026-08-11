"use client";

import { useActionState } from "react";

import { deleteAddressAction } from "@/app/actions/address";
import { Button } from "@/components/ui/button";
import type { Address } from "@/lib/api";

/**
 * The saved address book, with removal.
 *
 * Each row owns its own useActionState rather than the list sharing one. With a
 * single shared state, failing to delete address A would print the error next to
 * address B as well -- the error has to belong to the row that produced it.
 */
function AddressRow({ address }: { address: Address }) {
  const [state, formAction, pending] = useActionState(deleteAddressAction, {});

  const lines = [
    address.line1,
    address.line2,
    [address.city, address.state, address.postal_code].filter(Boolean).join(", "),
    address.country,
  ].filter(Boolean);

  return (
    <li className="flex flex-wrap items-start justify-between gap-4 border-b border-border py-4">
      <div className="min-w-0">
        <address className="font-body text-sm not-italic text-text">
          {lines.map((line) => (
            <span key={line} className="block">
              {line}
            </span>
          ))}
        </address>

        <p className="mt-2 flex items-center gap-2 font-body text-xs uppercase tracking-tight text-muted">
          <span>{address.type}</span>
          {address.is_default && (
            <span className="rounded-sm border border-border px-2 py-0.5">
              Default
            </span>
          )}
        </p>

        {state.error && (
          <p role="alert" className="mt-2 font-body text-sm text-error">
            {state.error}
          </p>
        )}
      </div>

      <form action={formAction}>
        <input type="hidden" name="address_id" value={address.id} />
        <Button type="submit" variant="ghost" size="sm" disabled={pending}>
          {pending ? "Removing..." : "Remove"}
        </Button>
      </form>
    </li>
  );
}

export function AddressList({ addresses }: { addresses: Address[] }) {
  if (addresses.length === 0) {
    return (
      <p className="mt-4 font-body text-sm text-muted">
        No saved addresses yet.
      </p>
    );
  }

  return (
    <ul className="mt-4 flex flex-col">
      {addresses.map((a) => (
        <AddressRow key={a.id} address={a} />
      ))}
    </ul>
  );
}
