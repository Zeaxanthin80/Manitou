import Link from "next/link";

import { ResetPasswordForm } from "@/components/password-reset-forms";

export const metadata = { title: "Choose a new password" };

/**
 * Landing page for the emailed link.
 *
 * The token arrives as a query param, which is how a link in an email can carry
 * it at all. It is single-use and expires in 30 minutes, so its presence in
 * browser history is bounded -- and completing the reset spends it immediately.
 */
export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;

  return (
    <main className="mx-auto max-w-md px-6 py-16">
      <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
        Choose a new password
      </h1>

      {token ? (
        <div className="mt-8">
          <ResetPasswordForm token={token} />
        </div>
      ) : (
        <>
          <p className="mt-4 font-body text-base text-muted">
            This page needs the link from your email. Open the message and click
            the link, or request a new one.
          </p>
          <Link
            href="/forgot-password"
            className="mt-6 inline-block font-body text-sm text-accent underline underline-offset-4"
          >
            Request a new link
          </Link>
        </>
      )}
    </main>
  );
}
