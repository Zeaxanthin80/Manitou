"use client";

import { useActionState } from "react";

import { updateOrderStatusAction } from "@/app/actions/admin";
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
    </div>
  );
}
