import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { AdminUserActions } from "@/components/admin-user-actions";
import { OrderStatus } from "@/components/order-status";
import { Card, CardBody } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ApiError, getAdminUser, listAuditEvents } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { getSession } from "@/lib/session";

/** One account, everything the vendor can see and do about it. */
export default async function AdminUserPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const token = await getSession();
  if (!token) redirect("/login");

  const { id } = await params;
  const userId = Number(id);
  if (!Number.isInteger(userId)) notFound();

  let user, history;
  try {
    [user, history] = await Promise.all([
      getAdminUser(token, userId),
      // This user's own slice of the trail. The target index from task 1 exists
      // for exactly this query.
      listAuditEvents(token, { target_type: "user", target_id: userId, limit: 20 }),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && [403, 404].includes(error.status)) notFound();
    throw error;
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <Link
        href="/admin/users"
        className="font-body text-xs uppercase tracking-wide text-muted hover:text-text"
      >
        &larr; All users
      </Link>

      <div className="mt-4 flex flex-wrap items-center gap-4">
        <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
          {user.full_name}
        </h1>
        {!user.is_active && (
          <span className="rounded-sm border border-accent px-2 py-1 font-body text-xs uppercase tracking-wide text-accent">
            Suspended
          </span>
        )}
        {user.role === "admin" && (
          <span className="rounded-sm border border-border px-2 py-1 font-body text-xs uppercase tracking-wide text-muted">
            Admin
          </span>
        )}
      </div>
      <p className="mt-2 font-body text-sm text-muted">{user.email}</p>

      <div className="mt-10 grid gap-12 lg:grid-cols-[1fr_18rem]">
        <div className="flex flex-col gap-12">
          <section>
            <h2 className="mb-4 font-body text-sm uppercase tracking-tight text-muted">
              Actions
            </h2>
            <AdminUserActions user={user} />
          </section>

          <section>
            <h2 className="mb-4 font-body text-sm uppercase tracking-tight text-muted">
              Recent orders
            </h2>
            {user.recent_orders.length === 0 ? (
              <p className="font-body text-sm text-muted">No orders yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <THead>
                    <TR>
                      <TH>Order</TH>
                      <TH>Placed</TH>
                      <TH>Status</TH>
                      <TH className="text-right">Total</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {user.recent_orders.map((o) => (
                      <TR key={o.id}>
                        <TD>
                          <Link
                            href={`/admin/orders/${o.id}`}
                            className="font-display text-sm uppercase tracking-tight text-text hover:text-accent"
                          >
                            #{o.id}
                          </Link>
                        </TD>
                        <TD className="whitespace-nowrap text-muted">
                          {new Date(o.created_at).toLocaleDateString(undefined, {
                            year: "numeric",
                            month: "short",
                            day: "numeric",
                          })}
                        </TD>
                        <TD>
                          <OrderStatus status={o.status} />
                        </TD>
                        <TD className="text-right font-display">
                          {formatMoney(o.total)}
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </div>
            )}
          </section>

          <section>
            <h2 className="mb-4 font-body text-sm uppercase tracking-tight text-muted">
              History
            </h2>
            {history.items.length === 0 ? (
              <p className="font-body text-sm text-muted">
                Nothing recorded for this account yet.
              </p>
            ) : (
              <ul className="flex flex-col">
                {history.items.map((e) => (
                  <li key={e.id} className="border-b border-border py-3">
                    <p className="font-body text-sm text-text">{e.action}</p>
                    <p className="font-body text-xs text-muted">
                      {new Date(e.created_at).toLocaleString()} &middot; by{" "}
                      {e.actor_email}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <aside className="flex flex-col gap-6">
          <Card>
            <CardBody>
              <dl className="flex flex-col gap-3 font-body text-sm">
                {[
                  ["Orders", String(user.order_count)],
                  ["Lifetime value", formatMoney(user.lifetime_value)],
                  ["Phone", user.phone ?? "—"],
                  ["Two-factor", user.totp_enabled ? "On" : "Off"],
                  [
                    "Joined",
                    new Date(user.created_at).toLocaleDateString(undefined, {
                      year: "numeric",
                      month: "long",
                    }),
                  ],
                ].map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-4">
                    <dt className="text-muted">{label}</dt>
                    <dd className="text-right text-text">{value}</dd>
                  </div>
                ))}
              </dl>
            </CardBody>
          </Card>

          {user.addresses.length > 0 && (
            <Card>
              <CardBody>
                <h2 className="font-body text-xs uppercase tracking-wide text-muted">
                  Addresses
                </h2>
                <ul className="mt-3 flex flex-col gap-3">
                  {user.addresses.map((a) => (
                    <li key={a.id} className="font-body text-sm text-text">
                      {[a.line1, a.city, a.postal_code, a.country]
                        .filter(Boolean)
                        .join(", ")}
                    </li>
                  ))}
                </ul>
              </CardBody>
            </Card>
          )}
        </aside>
      </div>
    </main>
  );
}
