import Link from "next/link";

import { loginAction, mfaPending } from "@/app/actions/auth";
import { AuthForm } from "@/components/auth-form";
import { MfaForm } from "@/components/mfa-form";

/**
 * Sign in, in one or two steps.
 *
 * Which step renders is decided by whether a challenge cookie is pending, not by
 * client state -- so a refresh mid-sign-in lands back on the code step rather
 * than starting over.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ reset?: string }>;
}) {
  const { reset } = await searchParams;

  if (await mfaPending()) {
    return (
      <main className="mx-auto max-w-md px-6 py-16">
        <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
          Enter your code
        </h1>
        <p className="mt-4 font-body text-base text-muted">
          Your password was accepted. One more step.
        </p>
        <div className="mt-8">
          <MfaForm />
        </div>
        <p className="mt-8 font-body text-sm text-muted">
          Lost your device?{" "}
          <Link href="/forgot-password" className="text-accent underline underline-offset-4">
            Use a recovery code above, or reset your password
          </Link>
        </p>
      </main>
    );
  }

  return (
    <>
      {reset && (
        <p
          role="status"
          className="mx-auto max-w-md px-6 pt-12 font-body text-sm text-text"
        >
          Your password has been changed. Sign in with it below.
        </p>
      )}
      <AuthForm
        action={loginAction}
        title="Sign in"
        submitLabel="Sign in"
        footer={{ text: "No account?", href: "/register", label: "Create one" }}
        secondaryLink={{ href: "/forgot-password", label: "Forgot your password?" }}
      />
    </>
  );
}
