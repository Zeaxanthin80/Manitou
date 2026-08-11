import { registerAction } from "@/app/actions/auth";
import { AuthForm } from "@/components/auth-form";

export default function RegisterPage() {
  return (
    <AuthForm
      action={registerAction}
      title="Create account"
      submitLabel="Create account"
      includeName
      footer={{ text: "Already have an account?", href: "/login", label: "Sign in" }}
    />
  );
}
