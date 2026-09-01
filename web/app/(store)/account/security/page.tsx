import Link from "next/link";
import { redirect } from "next/navigation";

import { currentUser } from "@/app/actions/auth";
import {
  ChangeEmailForm,
  ChangePasswordForm,
  CloseAccountForm,
  TwoFactorSection,
} from "@/components/security-forms";

export const metadata = { title: "Security" };

/**
 * Everything that changes a credential, on one page away from everyday browsing.
 *
 * Separate from /account deliberately: closing an account and rotating a
 * password do not belong a scroll below your order history, where a mis-click
 * lives.
 */
export default async function SecurityPage() {
  const user = await currentUser();
  if (!user) redirect("/login");

  return (
    <main className="mx-auto max-w-4xl px-6 py-12">
      <Link
        href="/account"
        className="font-body text-xs uppercase tracking-tight text-muted hover:text-text"
      >
        &larr; Your account
      </Link>
      <h1 className="mt-4 font-display text-2xl uppercase leading-none tracking-tight text-text">
        Security
      </h1>

      <div className="mt-12 flex flex-col gap-14">
        <section>
          <h2 className="mb-4 font-body text-sm uppercase tracking-tight text-muted">
            Password
          </h2>
          <ChangePasswordForm email={user.email} />
        </section>

        <section>
          <h2 className="mb-4 font-body text-sm uppercase tracking-tight text-muted">
            Email address
          </h2>
          <ChangeEmailForm current={user.email} />
        </section>

        <section>
          <h2 className="mb-4 font-body text-sm uppercase tracking-tight text-muted">
            Two-factor authentication
          </h2>
          <TwoFactorSection enabled={user.totp_enabled} email={user.email} />
        </section>

        <section className="border-t border-border pt-10">
          <h2 className="mb-4 font-body text-sm uppercase tracking-tight text-muted">
            Close account
          </h2>
          <CloseAccountForm email={user.email} />
        </section>
      </div>
    </main>
  );
}
