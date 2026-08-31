import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // A leading underscore already means "required by a signature, deliberately
    // unused" -- useActionState hands every action a (prevState, formData) pair
    // whether it wants them or not. Teaching the linter the convention is better
    // than a disable comment at each site, which would also suppress genuine
    // unused variables that happen to sit nearby.
    rules: {
      // Severity left at the "warn" this config already inherited -- only the
      // underscore option is added here. CI runs eslint with --max-warnings 0,
      // so a warning still fails the build; the difference is that the policy
      // about what counts as an error stays the project's, not this rule's.
      "@typescript-eslint/no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
