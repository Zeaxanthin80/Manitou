"use client";

import { useActionState } from "react";

import { setProductActiveAction } from "@/app/actions/admin";
import { Button } from "@/components/ui/button";

/**
 * Hide or show a product.
 *
 * Labelled Deactivate, never Delete. The endpoint sets is_active = false and
 * nothing is removed -- it cannot be, because order_items points at this
 * product's variants and every one of those foreign keys is NO ACTION. A button
 * saying "Delete" would be describing something the system will not do.
 */
export function ProductVisibility({
  productId,
  slug,
  isActive,
}: {
  productId: number;
  slug: string;
  isActive: boolean;
}) {
  const [state, formAction, pending] = useActionState(setProductActiveAction, {});

  return (
    <div>
      <form action={formAction} className="flex flex-wrap items-center gap-4">
        <input type="hidden" name="product_id" value={productId} />
        <input type="hidden" name="slug" value={slug} />
        <input type="hidden" name="activate" value={isActive ? "false" : "true"} />
        <Button
          type="submit"
          variant={isActive ? "danger" : "primary"}
          disabled={pending}
        >
          {pending
            ? "Saving..."
            : isActive
              ? "Hide from store"
              : "Show in store"}
        </Button>
        <p className="font-body text-sm text-muted">
          {isActive
            ? "Hiding removes it from the storefront. Past orders keep it."
            : "Hidden from the storefront. Past orders still show it."}
        </p>
      </form>

      {state.error && (
        <p role="alert" className="mt-3 font-body text-sm text-error">
          {state.error}
        </p>
      )}
      {state.ok && (
        <p role="status" className="mt-3 font-body text-sm text-text">
          {state.ok}
        </p>
      )}
    </div>
  );
}
