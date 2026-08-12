"use client";

import { useActionState } from "react";

import { updateProfileAction } from "@/app/actions/account";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import type { User } from "@/lib/api";

/**
 * Name and phone. No password required.
 *
 * Email and password have their own page for a reason: demanding a password to
 * correct a phone number teaches people to type it into any box that asks.
 */
export function ProfileForm({ user }: { user: User }) {
  const [state, action, pending] = useActionState(updateProfileAction, {});

  return (
    <form action={action} className="flex max-w-md flex-col gap-4">
      <FormField id="full_name" label="Name" required>
        {(c) => (
          <Input {...c} name="full_name" defaultValue={user.full_name} autoComplete="name" />
        )}
      </FormField>
      <FormField id="phone" label="Phone" hint="Optional.">
        {(c) => (
          <Input {...c} name="phone" defaultValue={user.phone ?? ""} autoComplete="tel" />
        )}
      </FormField>

      {state.error && (
        <p role="alert" className="font-body text-sm text-error">
          {state.error}
        </p>
      )}
      {state.ok && (
        <p role="status" className="font-body text-sm text-text">
          {state.ok}
        </p>
      )}

      <div>
        <Button type="submit" variant="ghost" disabled={pending}>
          {pending ? "Saving..." : "Save details"}
        </Button>
      </div>
    </form>
  );
}
