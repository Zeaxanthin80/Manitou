"use client";

import { useActionState } from "react";

import { verifyMfaAction } from "@/app/actions/auth";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";

/**
 * The second step of signing in.
 *
 * The challenge itself is not here -- it lives in an httpOnly cookie the action
 * reads, so it never appears in the page source. This form carries only the
 * code the customer types.
 */
export function MfaForm() {
  const [state, action, pending] = useActionState(verifyMfaAction, {});

  return (
    <form action={action} className="flex flex-col gap-4">
      <FormField
        id="code"
        label="Authentication code"
        required
        hint="From your authenticator app, or one of your recovery codes."
      >
        {(c) => (
          <Input
            {...c}
            name="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
          />
        )}
      </FormField>

      {state.error && (
        <p role="alert" className="font-body text-sm text-error">
          {state.error}
        </p>
      )}

      <Button type="submit" size="lg" disabled={pending}>
        {pending ? "Checking..." : "Continue"}
      </Button>
    </form>
  );
}
