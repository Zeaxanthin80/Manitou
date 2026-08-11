import { formatMoney } from "@/lib/format";

/**
 * The money breakdown, shared by the cart, checkout and the receipt.
 *
 * Every figure is a string straight from the API. Nothing here adds, multiplies
 * or rounds -- see the note on the Cart type in lib/api.ts for why that rule is
 * absolute rather than stylistic.
 */
export function OrderTotals({
  subtotal,
  tax,
  shippingCost,
  total,
  className,
}: {
  subtotal: string;
  tax: string;
  shippingCost: string;
  total: string;
  className?: string;
}) {
  const rows = [
    { label: "Subtotal", value: subtotal },
    { label: "Tax", value: tax },
    { label: "Shipping", value: shippingCost },
  ];

  return (
    <dl className={className}>
      {rows.map((row) => (
        <div
          key={row.label}
          className="flex items-baseline justify-between py-1 font-body text-sm"
        >
          <dt className="text-muted">{row.label}</dt>
          <dd className="text-text">{formatMoney(row.value)}</dd>
        </div>
      ))}
      <div className="mt-2 flex items-baseline justify-between border-t border-border pt-3">
        <dt className="font-body text-sm uppercase tracking-tight text-muted">
          Total
        </dt>
        <dd className="font-display text-xl text-text">{formatMoney(total)}</dd>
      </div>
    </dl>
  );
}
