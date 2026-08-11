"use client";

import { useActionState } from "react";

import type { AdminActionState } from "@/app/actions/admin";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import type { AdminProduct, Category } from "@/lib/api";

/**
 * Create/edit form for a product's own fields.
 *
 * On create the API demands at least one variant (Field(min_length=1)), so the
 * opening variant is part of this form rather than a second step -- a product
 * with no variants is unsellable and the schema refuses to make one.
 *
 * On edit the variant fields disappear; variants get their own section, because
 * by then there are several and each is edited independently.
 */
export function ProductForm({
  action,
  categories,
  product,
  submitLabel,
}: {
  action: (
    prev: AdminActionState,
    formData: FormData,
  ) => Promise<AdminActionState>;
  categories: Category[];
  product?: AdminProduct;
  submitLabel: string;
}) {
  const [state, formAction, pending] = useActionState(action, {});
  const creating = !product;

  return (
    <form action={formAction} className="flex max-w-2xl flex-col gap-5">
      {product && (
        <input type="hidden" name="product_id" value={product.id} />
      )}

      <FormField id="name" label="Name" required>
        {(c) => <Input {...c} name="name" defaultValue={product?.name} />}
      </FormField>

      <FormField
        id="slug"
        label="Slug"
        required
        hint="The storefront URL: /products/<slug>. Must be unique."
      >
        {(c) => <Input {...c} name="slug" defaultValue={product?.slug} />}
      </FormField>

      <FormField id="description" label="Description">
        {(c) => (
          <textarea
            {...c}
            name="description"
            rows={4}
            defaultValue={product?.description ?? ""}
            className="rounded-md border border-border bg-surface px-3 py-2 font-body text-sm text-text"
          />
        )}
      </FormField>

      <div className="grid gap-5 sm:grid-cols-2">
        <FormField id="category_id" label="Category" required>
          {(c) => (
            <select
              {...c}
              name="category_id"
              defaultValue={product?.category_id ?? categories[0]?.id}
              className="rounded-md border border-border bg-surface px-3 py-2 font-body text-sm text-text"
            >
              {categories.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.name}
                </option>
              ))}
            </select>
          )}
        </FormField>

        <FormField
          id="base_price"
          label="Base price"
          required
          hint="Variants may override this."
        >
          {(c) => (
            // type="text" with inputMode, not type="number": a number input
            // hands back a float-formatted value in some browsers, and this is
            // going to a numeric(10,2) column. The string is passed through
            // untouched.
            <Input
              {...c}
              name="base_price"
              inputMode="decimal"
              placeholder="24.00"
              defaultValue={product?.base_price}
            />
          )}
        </FormField>
      </div>

      {creating && (
        <fieldset className="mt-2 flex flex-col gap-5 border-t border-border pt-6">
          <legend className="font-body text-sm uppercase tracking-tight text-muted">
            Opening variant
          </legend>
          <div className="grid gap-5 sm:grid-cols-2">
            <FormField id="sku" label="SKU" required>
              {(c) => <Input {...c} name="sku" placeholder="TEE-CLS-S-BLK" />}
            </FormField>
            <FormField id="variant_name" label="Variant name" required>
              {(c) => (
                <Input {...c} name="variant_name" placeholder="Small / Black" />
              )}
            </FormField>
            <FormField id="quantity_available" label="Opening stock">
              {(c) => (
                <Input {...c} name="quantity_available" inputMode="numeric" defaultValue={0} />
              )}
            </FormField>
            <FormField
              id="reorder_level"
              label="Reorder level"
              hint="Flagged as low when stock falls to this."
            >
              {(c) => (
                <Input {...c} name="reorder_level" inputMode="numeric" defaultValue={0} />
              )}
            </FormField>
          </div>
        </fieldset>
      )}

      {state.error && (
        <p role="alert" className="font-body text-sm text-error">
          {state.error}
        </p>
      )}
      {state.ok && (
        <p role="status" className="font-body text-sm text-text">
          {state.ok}
        </p>
      )}

      <div>
        <Button type="submit" size="lg" disabled={pending}>
          {pending ? "Saving..." : submitLabel}
        </Button>
      </div>
    </form>
  );
}
