import { loginAction } from "@/app/actions/auth";
import { AuthForm } from "@/components/auth-form";

export default function LoginPage() {
  return (
    <AuthForm
      action={loginAction}
      title="Sign in"
      submitLabel="Sign in"
      footer={{ text: "No account?", href: "/register", label: "Create one" }}
    />
  );
}
