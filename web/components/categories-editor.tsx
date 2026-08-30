"use client";

import { useActionState } from "react";

import { categoryAction, createCategoryAction } from "@/app/actions/admin";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import type { AdminCategory } from "@/lib/api";

/**
 * Category management — the screen whose absence was defect 23.
 *
 * On a database built by migrations alone there were no categories, no way to
 * make one, and `products.category_id` is NOT NULL. So every route to a first
 * product was closed and the only way out was a database client. Five phases
 * missed it because every environment anyone developed against had been seeded.
 *
 * **Rendered as a flat list with indentation, not a nested tree.** The API
 * returns parents before children and the depth is one in practice; a recursive
 * component would be more code to express the same two levels, and would make the
 * "move to" select — which needs every category as a flat option list — harder to
 * build, not easier.
 *
 * Each row is its own form. One form for the whole page would mean a single
 * submit rewriting every category at once, so a validation failure on one row
 * would reject the others' edits too.
 */
export function CategoriesEditor({ categories }: { categories: AdminCategory[] }) {
  const [addState, addAction, adding] = useActionState(createCategoryAction, {});
  const [rowState, rowAction, busy] = useActionState(categoryAction, {});

  const byId = new Map(categories.map((c) => [c.id, c]));
  const depth = (c: AdminCategory) => (c.parent_id === null ? 0 : 1);

  return (
    <section className="flex flex-col gap-8">
      <div>
        <h2 className="font-body text-sm uppercase tracking-tight text-muted">
          Categories
        </h2>

        {categories.length === 0 ? (
          <p className="mt-4 max-w-2xl font-body text-sm text-muted">
            No categories yet. Every product belongs to one, so this is the first
            thing to create — a single category is enough to start.
          </p>
        ) : (
          <ul className="mt-4 flex max-w-3xl flex-col divide-y divide-border border-y border-border">
            {categories.map((category) => (
              <li
                key={category.id}
                className="flex flex-wrap items-end gap-3 py-3"
                style={{ paddingLeft: `${depth(category) * 1.5}rem` }}
              >
                <form action={rowAction} className="flex flex-wrap items-end gap-3">
                  <input type="hidden" name="category_id" value={category.id} />

                  <label className="flex flex-col gap-1 font-body text-xs text-muted">
                    Name
                    <Input
                      name="name"
                      defaultValue={category.name}
                      required
                      className="w-48"
                    />
                  </label>

                  <label className="flex flex-col gap-1 font-body text-xs text-muted">
                    Inside
                    <select
                      name="parent_id"
                      defaultValue={category.parent_id ?? ""}
                      className="rounded-md border border-border bg-surface px-3 py-2 font-body text-sm text-text"
                    >
                      <option value="">— top level —</option>
                      {categories
                        // Its own descendants are omitted rather than offered and
                        // then refused: moving a category under its own child
                        // detaches the branch from every root, and the API returns
                        // 409 for it. Not listing them is the same rule, expressed
                        // where the vendor is choosing.
                        .filter((other) => other.id !== category.id
                                        && other.parent_id !== category.id)
                        .map((other) => (
                          <option key={other.id} value={other.id}>
                            {other.name}
                          </option>
                        ))}
                    </select>
                  </label>

                  <Button type="submit" variant="ghost" size="sm" disabled={busy}>
                    Save
                  </Button>
                </form>

                <span className="font-body text-xs text-muted">
                  /{category.slug} · {describeUse(category)}
                </span>

                <form action={rowAction}>
                  <input type="hidden" name="category_id" value={category.id} />
                  <input type="hidden" name="intent" value="delete" />
                  <Button
                    type="submit"
                    variant="ghost"
                    size="sm"
                    // Disabled rather than hidden, and the count beside it says
                    // why. A button that vanishes leaves the vendor wondering
                    // whether the feature exists; one that is disabled next to
                    // "3 products" explains itself.
                    disabled={busy || category.product_count > 0 || category.child_count > 0}
                  >
                    Remove
                  </Button>
                </form>
              </li>
            ))}
          </ul>
        )}

        {rowState.error && (
          <p role="alert" className="mt-3 font-body text-sm text-error">
            {rowState.error}
          </p>
        )}
        {rowState.ok && (
          <p role="status" className="mt-3 font-body text-sm text-text">
            {rowState.ok}
          </p>
        )}
      </div>

      <form action={addAction} className="grid max-w-md gap-4">
        <h2 className="font-body text-sm uppercase tracking-tight text-muted">
          Add a category
        </h2>

        <FormField id="new-name" label="Name" required>
          {(c) => <Input {...c} name="name" placeholder="T-Shirts" />}
        </FormField>

        <FormField
          id="new-slug"
          label="Web address"
          hint="Leave blank to build it from the name. Lowercase letters, numbers and hyphens."
        >
          {(c) => <Input {...c} name="slug" placeholder="t-shirts" />}
        </FormField>

        <FormField id="new-parent" label="Inside">
          {(c) => (
            <select
              {...c}
              name="parent_id"
              defaultValue=""
              className="w-full rounded-md border border-border bg-surface px-3 py-2 font-body text-base text-text"
            >
              <option value="">— top level —</option>
              {categories.map((option) => (
                <option key={option.id} value={option.id}>
                  {byId.get(option.parent_id ?? -1)
                    ? `${byId.get(option.parent_id ?? -1)!.name} / ${option.name}`
                    : option.name}
                </option>
              ))}
            </select>
          )}
        </FormField>

        {addState.error && (
          <p role="alert" className="font-body text-sm text-error">
            {addState.error}
          </p>
        )}
        {addState.ok && (
          <p role="status" className="font-body text-sm text-text">
            {addState.ok}
          </p>
        )}

        <div>
          <Button type="submit" variant="ghost" disabled={adding}>
            {adding ? "Adding..." : "Add category"}
          </Button>
        </div>
      </form>
    </section>
  );
}

/** What is inside a category, phrased so the Remove button explains itself. */
function describeUse(category: AdminCategory): string {
  const parts: string[] = [];
  if (category.product_count) {
    parts.push(`${category.product_count} product${category.product_count === 1 ? "" : "s"}`);
  }
  if (category.child_count) {
    parts.push(
      `${category.child_count} subcategor${category.child_count === 1 ? "y" : "ies"}`,
    );
  }
  return parts.length ? parts.join(", ") : "empty";
}
