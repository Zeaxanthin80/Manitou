"use client";

import { useActionState } from "react";

import { addVariantAction, updateVariantAction } from "@/app/actions/admin";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import type { AdminProduct, AdminVariant } from "@/lib/api";

/**
 * Variants on an existing product.
 *
 * There is no Remove. order_items holds a foreign key to product_variants with
 * NO ACTION, so a variant that has ever sold cannot be deleted without
 * destroying order history -- and a variant that has NOT sold is
 * indistinguishable here without another query. Retiring one means setting its
 * stock to 0 on the Inventory screen, which the storefront renders as
 * "Sold out".
 *
 * Each row is its own form and its own action state, so a duplicate-SKU error on
 * one variant does not print itself next to the others.
 */
function VariantRow({
  variant,
  productId,
  slug,
}: {
  variant: AdminVariant;
  productId: number;
  slug: string;
}) {
  const [state, formAction, pending] = useActionState(updateVariantAction, {});

  return (
    <TR>
      <TD>
        <form
          action={formAction}
          id={`variant-${variant.id}`}
          className="contents"
        >
          <input type="hidden" name="variant_id" value={variant.id} />
          <input type="hidden" name="product_id" value={productId} />
          <input type="hidden" name="slug" value={slug} />
          <Input
            name="variant_name"
            defaultValue={variant.variant_name}
            aria-label={`Name for ${variant.sku}`}
            className="w-full"
          />
        </form>
      </TD>
      <TD>
        <Input
          form={`variant-${variant.id}`}
          name="sku"
          defaultValue={variant.sku}
          aria-label={`SKU for ${variant.sku}`}
          className="w-full"
        />
      </TD>
      <TD>
        <Input
          form={`variant-${variant.id}`}
          name="price_override"
          inputMode="decimal"
          placeholder="base price"
          defaultValue={variant.price_override ?? ""}
          aria-label={`Price override for ${variant.sku}`}
          className="w-full"
        />
      </TD>
      <TD className="text-right">
        <span className={variant.needs_reorder ? "text-accent" : undefined}>
          {variant.quantity_available}
        </span>
      </TD>
      <TD>
        <Button
          form={`variant-${variant.id}`}
          type="submit"
          variant="ghost"
          size="sm"
          disabled={pending}
        >
          {pending ? "Saving..." : "Save"}
        </Button>
        {state.error && (
          <p role="alert" className="mt-1 font-body text-xs text-error">
            {state.error}
          </p>
        )}
        {state.ok && (
          <p role="status" className="mt-1 font-body text-xs text-muted">
            Saved
          </p>
        )}
      </TD>
    </TR>
  );
}

export function ProductVariantsEditor({ product }: { product: AdminProduct }) {
  const [state, formAction, pending] = useActionState(addVariantAction, {});

  return (
    <section>
      <h2 className="font-body text-sm uppercase tracking-tight text-muted">
        Variants
      </h2>

      <div className="mt-4 overflow-x-auto">
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>SKU</TH>
              <TH>Price override</TH>
              <TH className="text-right">Stock</TH>
              <TH>
                <span className="sr-only">Actions</span>
              </TH>
            </TR>
          </THead>
          <TBody>
            {product.variants.map((v) => (
              <VariantRow
                key={v.id}
                variant={v}
                productId={product.id}
                slug={product.slug}
              />
            ))}
          </TBody>
        </Table>
      </div>

      <details className="mt-6">
        <summary className="cursor-pointer font-body text-sm uppercase tracking-tight text-muted hover:text-text">
          Add a variant
        </summary>
        <form action={formAction} className="mt-4 grid max-w-3xl gap-4 sm:grid-cols-2">
          <input type="hidden" name="product_id" value={product.id} />
          <input type="hidden" name="slug" value={product.slug} />
          <label className="flex flex-col gap-1 font-body text-sm text-text">
            SKU
            <Input name="sku" required placeholder="TEE-CLS-XL-BLK" />
          </label>
          <label className="flex flex-col gap-1 font-body text-sm text-text">
            Variant name
            <Input name="variant_name" required placeholder="XL / Black" />
          </label>
          <label className="flex flex-col gap-1 font-body text-sm text-text">
            Opening stock
            <Input name="quantity_available" inputMode="numeric" defaultValue={0} />
          </label>
          <label className="flex flex-col gap-1 font-body text-sm text-text">
            Reorder level
            <Input name="reorder_level" inputMode="numeric" defaultValue={0} />
          </label>

          {state.error && (
            <p role="alert" className="font-body text-sm text-error sm:col-span-2">
              {state.error}
            </p>
          )}
          {state.ok && (
            <p role="status" className="font-body text-sm text-text sm:col-span-2">
              {state.ok}
            </p>
          )}

          <div className="sm:col-span-2">
            <Button type="submit" variant="ghost" disabled={pending}>
              {pending ? "Adding..." : "Add variant"}
            </Button>
          </div>
        </form>
      </details>
    </section>
  );
}
