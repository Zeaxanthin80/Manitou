"use client";

import { useActionState, useState } from "react";

import {
  anonymiseUserAction,
  disableUserTwoFactorAction,
  sendUserPasswordResetAction,
  updateUserAction,
} from "@/app/actions/admin";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import type { AdminUserDetail } from "@/lib/api";

/**
 * One control per entry in `allowed_actions`, and nothing else.
 *
 * The API decides what is legal; this component never works it out. That is the
 * same contract as OrderStatusActions, and it is what turns the lockout guards
 * from something enforced into something visible: viewing your own row, there
 * simply is no suspend button, because the API did not offer one. A UI that
 * computed the rules itself would eventually disagree and start showing buttons
 * that 409.
 */

function Feedback({ error, ok }: { error?: string; ok?: string }) {
  return (
    <>
      {error && (
        <p role="alert" className="mt-3 font-body text-sm text-error">
          {error}
        </p>
      )}
      {ok && (
        <p role="status" className="mt-3 font-body text-sm text-text">
          {ok}
        </p>
      )}
    </>
  );
}

const LABELS: Record<string, string> = {
  suspend: "Suspend account",
  reactivate: "Reactivate account",
  promote: "Make admin",
  demote: "Remove admin",
};

export function AdminUserActions({ user }: { user: AdminUserDetail }) {
  const [state, act, pending] = useActionState(updateUserAction, {});
  const [resetState, sendReset, resetting] = useActionState(
    sendUserPasswordResetAction,
    {},
  );
  const [tfaState, disableTfa, disablingTfa] = useActionState(
    disableUserTwoFactorAction,
    {},
  );

  const allowed = new Set(user.allowed_actions);
  const stateChanges = (["suspend", "reactivate", "promote", "demote"] as const).filter(
    (a) => allowed.has(a),
  );

  return (
    <div className="flex flex-col gap-8">
      {stateChanges.length > 0 && (
        <div>
          <div className="flex flex-wrap gap-3">
            {stateChanges.map((intent) => (
              // A form each, so the intent travels as a field and no client
              // state is needed to remember which button was pressed.
              <form key={intent} action={act}>
                <input type="hidden" name="user_id" value={user.id} />
                <input type="hidden" name="intent" value={intent} />
                <Button
                  type="submit"
                  variant={intent === "suspend" ? "danger" : "ghost"}
                  disabled={pending}
                >
                  {LABELS[intent]}
                </Button>
              </form>
            ))}
          </div>
          <Feedback {...state} />
        </div>
      )}

      <div className="flex flex-wrap items-start gap-3">
        {allowed.has("password_reset") && (
          <form action={sendReset}>
            <input type="hidden" name="user_id" value={user.id} />
            <Button type="submit" variant="ghost" disabled={resetting}>
              {resetting ? "Sending..." : "Send password reset"}
            </Button>
          </form>
        )}
        {allowed.has("disable_2fa") && (
          <form action={disableTfa}>
            <input type="hidden" name="user_id" value={user.id} />
            <Button type="submit" variant="ghost" disabled={disablingTfa}>
              {disablingTfa ? "Turning off..." : "Turn off two-factor"}
            </Button>
          </form>
        )}
      </div>
      <Feedback {...resetState} />
      <Feedback {...tfaState} />

      {allowed.has("anonymise") && <AnonymiseForm user={user} />}
    </div>
  );
}

function AnonymiseForm({ user }: { user: AdminUserDetail }) {
  const [state, act, pending] = useActionState(anonymiseUserAction, {});
  const [password, setPassword] = useState("");
  const [confirmEmail, setConfirmEmail] = useState("");
  // Typing the target's address, not a generic word. An admin reaches this from
  // a list of users, so the mistake to guard against is erasing the wrong row --
  // which a password prompt does nothing about, since the password is correct
  // either way.
  const armed = password.length > 0 && confirmEmail.trim() === user.email;

  return (
    <details className="border-t border-border pt-6">
      <summary className="cursor-pointer font-body text-sm uppercase tracking-tight text-accent hover:text-error">
        Anonymise this account
      </summary>
      <form action={act} className="mt-4 flex max-w-md flex-col gap-4">
        <input type="hidden" name="user_id" value={user.id} />
        <input type="hidden" name="expected_email" value={user.email} />

        <p className="font-body text-sm text-muted">
          Irreversible. Removes their name, email and phone. Their orders are
          kept, without their details, because tax rules require keeping
          receipts. Addresses used by an order stay too — those are the shipping
          record.
        </p>

        <FormField id="anon_password" label="Your password" required>
          {(c) => (
            <Input
              {...c}
              name="current_password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </FormField>
        <FormField
          id="confirm_email"
          label="Type their email to confirm"
          required
          hint={user.email}
        >
          {(c) => (
            <Input
              {...c}
              name="confirm_email"
              value={confirmEmail}
              onChange={(e) => setConfirmEmail(e.target.value)}
            />
          )}
        </FormField>

        <Feedback {...state} />
        <div>
          <Button type="submit" variant="danger" disabled={pending || !armed}>
            {pending ? "Anonymising..." : "Anonymise account"}
          </Button>
        </div>
      </form>
    </details>
  );
}
