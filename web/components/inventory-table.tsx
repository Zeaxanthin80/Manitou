"use client";

import Link from "next/link";
import { useActionState } from "react";

import { updateInventoryAction } from "@/app/actions/admin";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SortableTH, Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { cn } from "@/lib/cn";

export type InventoryRow = {
  variantId: number;
  sku: string;
  variantName: string;
  productId: number;
  productName: string;
  productSlug: string;
  productActive: boolean;
  quantityAvailable: number;
  reorderLevel: number;
  needsReorder: boolean;
};

/**
 * Stock levels, one row per variant.
 *
 * Stock is entered as an ABSOLUTE count, not a +/- adjustment. The vendor is
 * recording a number they counted on a shelf. A delta would have to be applied
 * on top of whatever the value is at the moment it lands, which is a
 * read-modify-write -- and the only place this project does that is checkout,
 * under SELECT ... FOR UPDATE, because that one genuinely races.
 *
 * Each row owns its own action state so an error belongs to the row that caused
 * it, the same reason the address list and variant editor do it that way.
 */
function Row({ row }: { row: InventoryRow }) {
  const [state, formAction, pending] = useActionState(updateInventoryAction, {});
  const formId = `inv-${row.variantId}`;

  return (
    <TR className={row.needsReorder ? "bg-background" : undefined}>
      <TD>
        <form action={formAction} id={formId} className="contents">
          <input type="hidden" name="variant_id" value={row.variantId} />
          <input type="hidden" name="slug" value={row.productSlug} />
        </form>
        <Link
          href={`/admin/products/${row.productId}`}
          className={cn(
            "font-display text-sm uppercase tracking-tight hover:text-accent",
            row.productActive ? "text-text" : "text-muted",
          )}
        >
          {row.productName}
        </Link>
        {!row.productActive && (
          <span className="ml-2 font-body text-xs uppercase tracking-tight text-muted">
            hidden
          </span>
        )}
        <span className="block font-body text-sm text-muted">
          {row.variantName}
        </span>
      </TD>

      <TD className="font-body text-sm text-muted">{row.sku}</TD>

      <TD>
        <Input
          form={formId}
          name="quantity_available"
          inputMode="numeric"
          defaultValue={row.quantityAvailable}
          aria-label={`Stock for ${row.sku}`}
          className="w-24"
        />
      </TD>

      <TD>
        <Input
          form={formId}
          name="reorder_level"
          inputMode="numeric"
          defaultValue={row.reorderLevel}
          aria-label={`Reorder level for ${row.sku}`}
          className="w-24"
        />
      </TD>

      <TD>
        {row.quantityAvailable === 0 ? (
          <span className="rounded-sm border border-accent px-2 py-1 font-body text-xs uppercase tracking-tight text-accent">
            Out of stock
          </span>
        ) : row.needsReorder ? (
          <span className="rounded-sm border border-accent px-2 py-1 font-body text-xs uppercase tracking-tight text-accent">
            Reorder
          </span>
        ) : (
          <span className="font-body text-xs uppercase tracking-tight text-muted">
            OK
          </span>
        )}
      </TD>

      <TD>
        <Button form={formId} type="submit" variant="ghost" size="sm" disabled={pending}>
          {pending ? "Saving..." : "Save"}
        </Button>
        {state.error && (
          <p role="alert" className="mt-1 font-body text-xs text-error">
            {state.error}
          </p>
        )}
        {state.ok && (
          <p role="status" className="mt-1 font-body text-xs text-muted">
            {state.ok}
          </p>
        )}
      </TD>
    </TR>
  );
}

const SORTS = [
  { column: "product", label: "Product" },
  { column: "sku", label: "SKU" },
  { column: "stock", label: "In stock" },
  { column: "reorder", label: "Reorder at" },
  { column: "status", label: "Status" },
];

export function InventoryTable({
  rows,
  sort,
  direction,
  params,
}: {
  rows: InventoryRow[];
  sort: string;
  direction: "asc" | "desc";
  /** Filter to preserve when a heading is clicked. */
  params?: Record<string, string | undefined>;
}) {
  if (rows.length === 0) {
    return (
      <p className="mt-10 font-body text-base text-muted">
        Nothing to show here.
      </p>
    );
  }

  return (
    <div className="mt-8 overflow-x-auto">
      <Table>
        <THead>
          <TR>
            {SORTS.map((s) => (
              <SortableTH
                key={s.column}
                column={s.column}
                label={s.label}
                sort={sort}
                direction={direction}
                basePath="/admin/inventory"
                params={params}
              />
            ))}
            {/* Holds the Save buttons. The heading is screen-reader-only: an
                actions column needs a name announced, not a word printed. */}
            <TH>
              <span className="sr-only">Actions</span>
            </TH>
          </TR>
        </THead>
        <TBody>
          {rows.map((r) => (
            <Row key={r.variantId} row={r} />
          ))}
        </TBody>
      </Table>
    </div>
  );
}
