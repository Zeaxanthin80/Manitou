import Link from "next/link";

import { ForgotPasswordForm } from "@/components/password-reset-forms";

export const metadata = { title: "Reset your password" };

export default function ForgotPasswordPage() {
  return (
    <main className="mx-auto max-w-md px-6 py-16">
      <h1 className="font-display text-2xl uppercase leading-none tracking-tight text-text">
        Reset your password
      </h1>
      <p className="mt-4 font-body text-base text-muted">
        Enter the address you signed up with and we will send you a link.
      </p>
      <div className="mt-8">
        <ForgotPasswordForm />
      </div>
      <p className="mt-8 font-body text-sm text-muted">
        Remembered it?{" "}
        <Link href="/login" className="text-accent underline underline-offset-4">
          Sign in
        </Link>
      </p>
    </main>
  );
}
