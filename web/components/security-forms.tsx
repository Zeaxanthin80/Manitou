"use client";

import Image from "next/image";
import { useActionState, useState } from "react";

import {
  changeEmailAction,
  changePasswordAction,
  closeAccountAction,
  disableTwoFactorAction,
  enableTwoFactorAction,
  startTwoFactorAction,
} from "@/app/actions/account";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";

/** Shared feedback block, so every form on this page reports the same way. */
function Feedback({ error, ok }: { error?: string; ok?: string }) {
  return (
    <>
      {error && (
        <p role="alert" className="font-body text-sm text-error">
          {error}
        </p>
      )}
      {ok && (
        <p role="status" className="font-body text-sm text-text">
          {ok}
        </p>
      )}
    </>
  );
}

export function ChangePasswordForm() {
  const [state, action, pending] = useActionState(changePasswordAction, {});

  return (
    <form action={action} className="flex max-w-md flex-col gap-4">
      <FormField id="current_password" label="Current password" required>
        {(c) => (
          <PasswordInput
            {...c}
            name="current_password"
            autoComplete="current-password"
          />
        )}
      </FormField>
      <FormField
        id="new_password"
        label="New password"
        required
        hint="At least 8 characters."
      >
        {(c) => (
          <PasswordInput
            {...c}
            name="new_password"
            autoComplete="new-password"
            minLength={8}
          />
        )}
      </FormField>
      <Feedback {...state} />
      <div>
        <Button type="submit" disabled={pending}>
          {pending ? "Changing..." : "Change password"}
        </Button>
      </div>
      <p className="font-body text-xs text-muted">
        Changing your password signs you out everywhere else. This device stays
        signed in.
      </p>
    </form>
  );
}

export function ChangeEmailForm({ current }: { current: string }) {
  const [state, action, pending] = useActionState(changeEmailAction, {});

  return (
    <form action={action} className="flex max-w-md flex-col gap-4">
      <p className="font-body text-sm text-muted">
        Currently <span className="text-text">{current}</span>
      </p>
      <FormField id="new_email" label="New email" required>
        {(c) => <Input {...c} name="new_email" type="email" autoComplete="email" />}
      </FormField>
      <FormField id="email_password" label="Current password" required>
        {(c) => (
          <PasswordInput
            {...c}
            name="current_password"
            autoComplete="current-password"
          />
        )}
      </FormField>
      <Feedback {...state} />
      <div>
        <Button type="submit" disabled={pending}>
          {pending ? "Changing..." : "Change email"}
        </Button>
      </div>
      <p className="font-body text-xs text-muted">
        We will tell your current address that it changed. Check the new address
        is right — you will sign in with it from now on.
      </p>
    </form>
  );
}

export function TwoFactorSection({ enabled }: { enabled: boolean }) {
  const [setupState, startSetup, starting] = useActionState(startTwoFactorAction, {});
  const [enableState, enable, enabling] = useActionState(enableTwoFactorAction, {});
  const [offState, disable, disabling] = useActionState(disableTwoFactorAction, {});

  // Once enabled, the codes come back in enableState and are never retrievable
  // again -- so they are rendered from the action result, not fetched.
  if (enableState.recoveryCodes) {
    return (
      <div className="max-w-md">
        <p role="status" className="font-body text-sm text-text">
          {enableState.ok}
        </p>
        <p className="mt-4 font-body text-sm text-muted">
          Save these recovery codes somewhere safe. Each works once, and this is
          the only time they are shown — we store them hashed and cannot show
          them again.
        </p>
        <ul className="mt-4 grid grid-cols-2 gap-2 rounded-md border border-border bg-background p-4">
          {enableState.recoveryCodes.map((code) => (
            <li key={code} className="font-body text-sm text-text">
              {code}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (enabled) {
    return (
      <form action={disable} className="flex max-w-md flex-col gap-4">
        <p className="font-body text-sm text-text">
          Two-factor authentication is <strong>on</strong>. You are asked for a
          code each time you sign in.
        </p>
        <FormField id="disable_password" label="Current password" required>
          {(c) => (
            <PasswordInput
              {...c}
              name="current_password"
              autoComplete="current-password"
            />
          )}
        </FormField>
        <Feedback {...offState} />
        <div>
          <Button type="submit" variant="danger" disabled={disabling}>
            {disabling ? "Turning off..." : "Turn off two-factor"}
          </Button>
        </div>
        <p className="font-body text-xs text-muted">
          Your password, not a code — the usual reason to turn this off is that
          you no longer have the authenticator.
        </p>
      </form>
    );
  }

  if (setupState.setup) {
    return (
      <div className="flex max-w-md flex-col gap-4">
        <p className="font-body text-sm text-muted">
          Scan this with your authenticator app, then enter the six-digit code it
          shows.
        </p>
        <div className="relative size-48 overflow-hidden rounded-md border border-border bg-surface">
          <Image
            src={setupState.setup.qr_data_uri}
            alt="QR code for setting up two-factor authentication"
            fill
            sizes="192px"
            unoptimized
          />
        </div>
        <details>
          <summary className="cursor-pointer font-body text-xs uppercase tracking-tight text-muted hover:text-text">
            Can&apos;t scan? Enter this instead
          </summary>
          <p className="mt-2 font-body text-sm break-all text-text">
            {setupState.setup.secret}
          </p>
        </details>

        <form action={enable} className="flex flex-col gap-4">
          <FormField id="code" label="Six-digit code" required>
            {(c) => (
              <Input
                {...c}
                name="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                minLength={6}
                className="w-32"
              />
            )}
          </FormField>
          <Feedback {...enableState} />
          <div>
            <Button type="submit" disabled={enabling}>
              {enabling ? "Checking..." : "Turn on two-factor"}
            </Button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <form action={startSetup} className="max-w-md">
      <p className="font-body text-sm text-muted">
        Two-factor authentication is off. With it on, signing in asks for a code
        from your phone as well as your password.
      </p>
      <Feedback {...setupState} />
      <Button type="submit" variant="ghost" className="mt-4" disabled={starting}>
        {starting ? "Preparing..." : "Set up two-factor"}
      </Button>
    </form>
  );
}

export function CloseAccountForm() {
  const [state, action, pending] = useActionState(closeAccountAction, {});
  // Both fields must be filled before the button arms. The API already demands
  // the password; this is the UI refusing to make something irreversible a
  // one-click affair.
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const armed = password.length > 0 && confirm === "DELETE";

  return (
    <details>
      <summary className="cursor-pointer font-body text-sm uppercase tracking-tight text-accent hover:text-error">
        Close my account
      </summary>
      <form action={action} className="mt-4 flex max-w-md flex-col gap-4">
        <p className="font-body text-sm text-muted">
          This cannot be undone. Your name, email and phone number are removed.
          Past orders are kept, without your details attached, because tax rules
          require keeping receipts.
        </p>
        <FormField id="close_password" label="Current password" required>
          {(c) => (
            <PasswordInput
              {...c}
              name="current_password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </FormField>
        <FormField id="confirm" label="Type DELETE to confirm" required>
          {(c) => (
            <Input
              {...c}
              name="confirm"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          )}
        </FormField>
        <Feedback {...state} />
        <div>
          <Button type="submit" variant="danger" disabled={pending || !armed}>
            {pending ? "Closing..." : "Close account"}
          </Button>
        </div>
      </form>
    </details>
  );
}
