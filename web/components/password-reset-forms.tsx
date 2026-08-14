"use client";

import { useActionState } from "react";

import { forgotPasswordAction, resetPasswordAction } from "@/app/actions/account";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";

export function ForgotPasswordForm() {
  const [state, action, pending] = useActionState(forgotPasswordAction, {});

  // Once the API has answered, stop showing the form. It replies identically for
  // a known address, an unknown one and a suspended account, so re-offering the
  // field would invite someone to try another address and compare -- which is
  // exactly the enumeration the identical response exists to prevent.
  if (state.ok) {
    return (
      <div>
        <p role="status" className="font-body text-base text-text">
          {state.ok}
        </p>
        <p className="mt-4 font-body text-sm text-muted">
          The link works once and expires in 30 minutes. Check your spam folder
          if it does not arrive.
        </p>
      </div>
    );
  }

  return (
    <form action={action} className="flex flex-col gap-4">
      <FormField id="email" label="Email" required>
        {(c) => <Input {...c} name="email" type="email" autoComplete="email" />}
      </FormField>
      {state.error && (
        <p role="alert" className="font-body text-sm text-error">
          {state.error}
        </p>
      )}
      <Button type="submit" size="lg" disabled={pending}>
        {pending ? "Sending..." : "Send reset link"}
      </Button>
    </form>
  );
}

export function ResetPasswordForm({ token }: { token: string }) {
  const [state, action, pending] = useActionState(resetPasswordAction, {});

  return (
    <form action={action} className="flex flex-col gap-4">
      {/* The token rides in a hidden field rather than being re-read from the
          URL by the action -- a Server Action receives form data, not the
          browser's address bar. */}
      <input type="hidden" name="token" value={token} />

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

      {state.error && (
        <p role="alert" className="font-body text-sm text-error">
          {state.error}
        </p>
      )}

      <Button type="submit" size="lg" disabled={pending}>
        {pending ? "Setting..." : "Set new password"}
      </Button>
      <p className="font-body text-xs text-muted">
        This signs you out on every device, then you sign in with the new
        password.
      </p>
    </form>
  );
}
