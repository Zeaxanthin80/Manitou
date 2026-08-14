"use client";

import Link from "next/link";
import { useActionState } from "react";

import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import type { FormState } from "@/app/actions/auth";

/**
 * Shared shell for login and register.
 *
 * useActionState gives the action's returned error and a `pending` flag with no
 * useState of our own. The form posts to the Server Action directly, so it works
 * before JavaScript loads -- progressive enhancement for free.
 */
export function AuthForm({
  action,
  title,
  submitLabel,
  includeName = false,
  footer,
  secondaryLink,
}: {
  action: (prev: FormState, data: FormData) => Promise<FormState>;
  title: string;
  submitLabel: string;
  includeName?: boolean;
  footer: { text: string; href: string; label: string };
  /** Optional extra link under the button -- "Forgot your password?" on sign in.
   *  Optional so the register page, which has no such flow, omits it entirely
   *  rather than passing something empty. */
  secondaryLink?: { href: string; label: string };
}) {
  const [state, formAction, pending] = useActionState(action, {});

  return (
    <main className="mx-auto max-w-sm px-6 py-12">
      <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
        {title}
      </h1>

      <form action={formAction} className="mt-8 flex flex-col gap-4">
        {includeName && (
          <FormField id="full_name" label="Full name" required>
            {(control) => <Input name="full_name" autoComplete="name" {...control} />}
          </FormField>
        )}

        <FormField id="email" label="Email" required>
          {(control) => (
            <Input name="email" type="email" autoComplete="email" {...control} />
          )}
        </FormField>

        <FormField
          id="password"
          label="Password"
          hint={includeName ? "At least 8 characters." : undefined}
          required
        >
          {(control) => (
            <PasswordInput
              name="password"
              // Tells a password manager whether to offer a saved password or
              // generate a new one.
              autoComplete={includeName ? "new-password" : "current-password"}
              {...control}
            />
          )}
        </FormField>

        {state.error && (
          // role="alert" so the failure is announced, not just shown.
          <p role="alert" className="font-body text-sm text-error">
            {state.error}
          </p>
        )}

        <Button type="submit" size="lg" disabled={pending}>
          {pending ? "Working..." : submitLabel}
        </Button>
      </form>

      <p className="mt-6 font-body text-sm text-muted">
        {secondaryLink && (
          <>
            <Link
              href={secondaryLink.href}
              className="text-accent underline underline-offset-4"
            >
              {secondaryLink.label}
            </Link>
            <br />
          </>
        )}
        {footer.text}{" "}
        <Link href={footer.href} className="text-accent underline underline-offset-4">
          {footer.label}
        </Link>
      </p>
    </main>
  );
}
