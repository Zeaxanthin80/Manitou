import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Pagination } from "@/components/pagination";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ApiError, listAuditEvents } from "@/lib/api";
import { getSession } from "@/lib/session";

const PER_PAGE = 50;

/**
 * The audit trail, read-only.
 *
 * There is deliberately no delete or edit control anywhere on this page, and no
 * API endpoint behind one: audit_events is append-only in the database via a
 * trigger. A UI offering to remove a row would imply a capability that does not
 * exist, and the point of the table is that it can be trusted after something
 * has gone wrong.
 *
 * The filter's options come from the API rather than a list kept here. `action`
 * is free text with no CHECK constraint, so any local copy would go stale the
 * first time a new one is recorded -- Phase 5's payment events will appear on
 * their own.
 */
export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string; action?: string }>;
}) {
  const token = await getSession();
  if (!token) redirect("/login");

  const { page, action } = await searchParams;
  const parsed = Number(page);
  const current = Number.isInteger(parsed) && parsed > 0 ? parsed : 1;

  let events;
  try {
    events = await listAuditEvents(token, {
      action,
      limit: PER_PAGE,
      offset: (current - 1) * PER_PAGE,
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && error.status === 403) notFound();
    throw error;
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
          Audit log
        </h1>
        <p className="font-body text-sm text-muted">
          {events.total} {events.total === 1 ? "event" : "events"}
          {action ? ` · ${action}` : ""}
        </p>
      </div>

      <p className="mt-3 max-w-prose font-body text-sm text-muted">
        Every consequential action, recorded as it happened. This log cannot be
        edited or deleted — not from here, and not by the API.
      </p>

      <form action="/admin/audit" className="mt-6 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 font-body text-xs uppercase tracking-wide text-muted">
          Action
          <select
            name="action"
            defaultValue={action ?? ""}
            className="w-72 rounded-md border border-border bg-surface px-3 py-2 font-body text-sm text-text"
          >
            <option value="">All actions</option>
            {events.actions.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          className="rounded-md border border-border px-4 py-2 font-body text-sm text-text hover:bg-background"
        >
          Filter
        </button>
        {action && (
          <Link
            href="/admin/audit"
            className="pb-2 font-body text-sm text-muted underline hover:text-text"
          >
            Clear
          </Link>
        )}
      </form>

      {events.items.length === 0 ? (
        <p className="mt-10 font-body text-base text-muted">Nothing recorded yet.</p>
      ) : (
        <>
          <div className="mt-8 overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH>When</TH>
                  <TH>Action</TH>
                  <TH>By</TH>
                  <TH>Target</TH>
                  <TH>Details</TH>
                </TR>
              </THead>
              <TBody>
                {events.items.map((e) => (
                  <TR key={e.id}>
                    <TD className="whitespace-nowrap text-muted">
                      {new Date(e.created_at).toLocaleString(undefined, {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </TD>
                    <TD className="font-body">{e.action}</TD>
                    <TD className="max-w-0 truncate text-muted" title={e.actor_email}>
                      {e.actor_email}
                    </TD>
                    <TD className="whitespace-nowrap text-muted">
                      {e.target_type === "user" && e.target_id ? (
                        <Link
                          href={`/admin/users/${e.target_id}`}
                          className="underline hover:text-text"
                        >
                          user #{e.target_id}
                        </Link>
                      ) : e.target_type === "order" && e.target_id ? (
                        <Link
                          href={`/admin/orders/${e.target_id}`}
                          className="underline hover:text-text"
                        >
                          order #{e.target_id}
                        </Link>
                      ) : (
                        `${e.target_type}${e.target_id ? ` #${e.target_id}` : ""}`
                      )}
                    </TD>
                    <TD className="max-w-xs truncate font-body text-xs text-muted">
                      {Object.entries(e.details)
                        .map(([k, v]) =>
                          v && typeof v === "object" && "from" in (v as object)
                            ? `${k}: ${(v as { from: string }).from} → ${(v as { to: string }).to}`
                            : `${k}: ${String(v)}`,
                        )
                        .join("  ") || "—"}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </div>

          <Pagination
            total={events.total}
            limit={events.limit}
            offset={events.offset}
            basePath="/admin/audit"
            params={{ action }}
          />
        </>
      )}
    </main>
  );
}
