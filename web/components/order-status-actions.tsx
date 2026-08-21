"use client";

import { useActionState } from "react";

import {
  recheckPaymentAction,
  updateOrderStatusAction,
} from "@/app/actions/admin";
import { Button } from "@/components/ui/button";

/**
 * The status-advance buttons.
 *
 * One button per entry in `allowed_transitions`, which the API computes from its
 * own ALLOWED_TRANSITIONS map. Nothing here decides what is legal -- if this
 * component held its own copy of the workflow it would eventually disagree with
 * the server and offer a button that 409s.
 *
 * `cancelled` and `refunded` are destructive-ish and get the danger variant;
 * everything else is a normal forward step.
 */
const DESTRUCTIVE = new Set(["cancelled", "refunded"]);

/**
 * Ask Stripe again.
 *
 * Rendered whatever the status, including terminal ones. A cancelled order can
 * still have money attached -- that is exactly the conflict case -- so hiding
 * this on anything but `pending` would hide it precisely when a vendor most
 * needs to know what Stripe thinks.
 *
 * Its own form and its own action state, so a re-check result never overwrites
 * the message from a status change or vice versa.
 */
function RecheckPayment({ orderId }: { orderId: number }) {
  const [state, formAction, pending] = useActionState(recheckPaymentAction, {});

  return (
    <div className="mt-6 border-t border-border pt-4">
      <form action={formAction}>
        <input type="hidden" name="order_id" value={orderId} />
        <Button type="submit" variant="ghost" size="sm" disabled={pending}>
          {pending ? "Checking Stripe..." : "Re-check payment"}
        </Button>
      </form>
      <p className="mt-2 max-w-prose font-body text-xs text-muted">
        Use this if an order looks unpaid but the customer says they paid. Stripe
        stops retrying a missed notification after a few days.
      </p>
      {state.ok && (
        <p role="status" className="mt-2 font-body text-sm text-text">
          {state.ok}
        </p>
      )}
      {state.error && (
        <p role="alert" className="mt-2 font-body text-sm text-error">
          {state.error}
        </p>
      )}
    </div>
  );
}

export function OrderStatusActions({
  orderId,
  allowed,
}: {
  orderId: number;
  allowed: string[];
}) {
  const [state, formAction, pending] = useActionState(updateOrderStatusAction, {});

  if (allowed.length === 0) {
    return (
      <div>
        <p className="font-body text-sm text-muted">
          This order has reached a final status. Nothing further to do.
        </p>
        {/* state.ok belongs here too: the move INTO a terminal status is made
            from this component, and after it re-renders there are no buttons
            left -- so without this the last transition of an order's life is the
            one that gives no confirmation. */}
        {state.ok && (
          <p role="status" className="mt-2 font-body text-sm text-text">
            {state.ok}
          </p>
        )}
        {state.error && (
          <p role="alert" className="mt-2 font-body text-sm text-error">
            {state.error}
          </p>
        )}
        <RecheckPayment orderId={orderId} />
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap gap-3">
        {allowed.map((status) => (
          // A separate form per button so each submits its own status without
          // needing client state to track which was clicked.
          <form key={status} action={formAction}>
            <input type="hidden" name="order_id" value={orderId} />
            <input type="hidden" name="status" value={status} />
            <Button
              type="submit"
              variant={DESTRUCTIVE.has(status) ? "danger" : "primary"}
              disabled={pending}
              className="capitalize"
            >
              {pending ? "Saving..." : `Mark ${status}`}
            </Button>
          </form>
        ))}
      </div>

      {/* role="status" for success and role="alert" for failure: the first is
          polite, the second interrupts. A vendor who just cancelled an order by
          mistake should hear about it immediately. */}
      {state.ok && (
        <p role="status" className="mt-3 font-body text-sm text-text">
          {state.ok}
        </p>
      )}
      {state.error && (
        <p role="alert" className="mt-3 font-body text-sm text-error">
          {state.error}
        </p>
      )}

      <RecheckPayment orderId={orderId} />
    </div>
  );
}
