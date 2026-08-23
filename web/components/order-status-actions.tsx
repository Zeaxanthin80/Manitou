"use client";

import { useActionState } from "react";

import {
  dispatchOrderAction,
  recheckPaymentAction,
  recordShipmentEventAction,
  updateOrderStatusAction,
} from "@/app/actions/admin";
import { storeConfig } from "@/lib/store-config";
import type { Shipment } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

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

/* Which transitions need evidence is the API's business, not this component's.
   It arrives as `evidenceRequired` beside `allowed`, computed from the same
   constant the PATCH guard raises on -- so the buttons offered here and the
   moves the server accepts cannot drift apart.

   What stays here is presentation: knowing that `shipped` is collected by a
   dispatch form rather than a button is a layout decision, and layout is the
   one thing this component is entitled to own. */

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

/**
 * Record a dispatch: carrier and tracking number.
 *
 * Replaces the old "Mark shipped" button. The carrier list comes from store
 * config -- the same list the API validates against -- so a UK clone editing
 * store-config.json changes both the picker and the guard with one edit.
 */
function DispatchForm({ orderId }: { orderId: number }) {
  const [state, formAction, pending] = useActionState(dispatchOrderAction, {});
  const carriers = storeConfig.fulfilment.carriers;

  return (
    <div className="mt-6 border-t border-border pt-4">
      <h3 className="font-body text-sm uppercase tracking-tight text-muted">
        Dispatch this order
      </h3>
      <p className="mt-1 mb-3 max-w-prose font-body text-xs text-muted">
        The carrier and tracking number are what answer a &ldquo;not
        received&rdquo; dispute. The order moves to shipped once recorded.
      </p>
      <form action={formAction} className="flex flex-wrap items-end gap-3">
        <input type="hidden" name="order_id" value={orderId} />
        <label className="flex flex-col gap-1">
          <span className="font-body text-xs uppercase tracking-tight text-muted">
            Carrier
          </span>
          <select
            name="carrier"
            defaultValue={carriers[0]?.code ?? ""}
            className="rounded-md border border-border bg-surface px-3 py-2 font-body text-sm text-text"
          >
            {carriers.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-body text-xs uppercase tracking-tight text-muted">
            Tracking number
          </span>
          <Input name="tracking_number" className="w-64" autoComplete="off" />
        </label>
        <Button type="submit" disabled={pending}>
          {pending ? "Recording..." : "Record dispatch"}
        </Button>
      </form>
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

/**
 * The parcel: where it is, and everything that has happened to it.
 *
 * `source` is shown on every line deliberately. A delivery an admin asserted is
 * not the same fact as one a carrier confirmed, and a timeline that hid the
 * difference would be exactly as misleading as the status word this phase
 * replaced.
 */
/**
 * The vendor's word for each event.
 *
 * `dispatched` is the DATABASE value -- a CHECK constraint accepts exactly six
 * strings and this is one of them. But the order badge on the same screen reads
 * SHIPPED, and two words for one thing reads as two things. So the schema keeps
 * its vocabulary and the screen uses the store's.
 *
 * Everything else already reads correctly once the underscores are removed,
 * which is why only one entry is here rather than all six.
 */
const EVENT_LABELS: Record<string, string> = { dispatched: "Shipped" };

function eventLabel(status: string): string {
  return EVENT_LABELS[status] ?? status.replace(/_/g, " ");
}

function ShipmentPanel({
  orderId,
  shipment,
}: {
  orderId: number;
  shipment: Shipment;
}) {
  const [state, formAction, pending] = useActionState(recordShipmentEventAction, {});
  const delivered = shipment.delivered_at !== null;

  return (
    <div className="mt-6 border-t border-border pt-4">
      <h3 className="font-body text-sm uppercase tracking-tight text-muted">
        Shipment
      </h3>

      <p className="mt-2 font-body text-sm text-text">
        {shipment.carrier_name ?? shipment.method}
        {shipment.tracking_number && (
          <>
            {" \u00b7 "}
            {shipment.tracking_url ? (
              <a
                href={shipment.tracking_url}
                target="_blank"
                rel="noreferrer noopener"
                className="underline underline-offset-4 hover:text-accent"
              >
                {shipment.tracking_number}
              </a>
            ) : (
              shipment.tracking_number
            )}
          </>
        )}
      </p>

      <ol className="mt-4 flex flex-col gap-2">
        {shipment.events.map((e) => (
          <li key={e.id} className="font-body text-sm">
            <span className="text-text capitalize">{eventLabel(e.status)}</span>
            <span className="text-muted">
              {" \u00b7 "}
              {new Date(e.occurred_at).toLocaleString()}
              {" \u00b7 "}
              {e.source}
              {e.actor_email ? ` (${e.actor_email})` : ""}
            </span>
          </li>
        ))}
      </ol>

      {!delivered && (
        <form action={formAction} className="mt-4 flex flex-wrap gap-3">
          <input type="hidden" name="order_id" value={orderId} />
          {["in_transit", "out_for_delivery", "delivered", "failed"].map((s) => (
            <button
              key={s}
              type="submit"
              name="status"
              value={s}
              disabled={pending}
              className="rounded-md border border-border bg-transparent px-2 py-1 font-body text-xs uppercase tracking-tight text-text hover:bg-background disabled:opacity-50"
            >
              {eventLabel(s)}
            </button>
          ))}
        </form>
      )}

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
  evidenceRequired,
  shipment,
}: {
  orderId: number;
  allowed: string[];
  /** Subset of `allowed` that PATCH refuses; each has its own endpoint. */
  evidenceRequired: string[];
  /** null until dispatched. Decides form vs panel. */
  shipment?: Shipment | null;
}) {
  const [state, formAction, pending] = useActionState(updateOrderStatusAction, {});

  const plain = allowed.filter((s) => !evidenceRequired.includes(s));

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
        {shipment && <ShipmentPanel orderId={orderId} shipment={shipment} />}
        <RecheckPayment orderId={orderId} />
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap gap-3">
        {plain.map((status) => (
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

      {/* Dispatch replaces the "Mark shipped" button the API now refuses.
          Rendered only when shipping is actually the legal next move, so it
          never appears on an unpaid or cancelled order. */}
      {allowed.includes("shipped") && !shipment && (
        <DispatchForm orderId={orderId} />
      )}

      {shipment && <ShipmentPanel orderId={orderId} shipment={shipment} />}

      <RecheckPayment orderId={orderId} />
    </div>
  );
}
