import { cn } from "@/lib/cn";

/**
 * Label + control + hint/error, correctly associated.
 *
 * This is the accessibility piece of the set. A <label> that is not
 * programmatically tied to its control is decoration: clicking it does not focus
 * the field, and a screen reader announces an unlabelled input. Likewise an
 * error rendered as loose red text is invisible to assistive tech unless
 * aria-describedby points at it.
 *
 * So the id flows down: label htmlFor -> control id -> aria-describedby -> the
 * hint or error node. The caller supplies one id and gets all of it.
 */

export type FormFieldProps = {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  className?: string;
  /** Receives the wiring to spread onto the control. */
  children: (control: {
    id: string;
    "aria-describedby"?: string;
    "aria-invalid"?: boolean;
    required?: boolean;
  }) => React.ReactNode;
};

export function FormField({
  id,
  label,
  hint,
  error,
  required,
  className,
  children,
}: FormFieldProps) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  // Both can apply at once; aria-describedby takes a space-separated list.
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <label htmlFor={id} className="font-body text-sm text-text">
        {label}
        {required && (
          <span className="text-error" aria-hidden="true">
            {" *"}
          </span>
        )}
      </label>

      {children({
        id,
        "aria-describedby": describedBy,
        "aria-invalid": error ? true : undefined,
        required,
      })}

      {hint && !error && (
        <p id={hintId} className="font-body text-xs text-muted">
          {hint}
        </p>
      )}
      {error && (
        // role="alert" so the message is announced when it appears, not only
        // when the field happens to be focused.
        <p id={errorId} role="alert" className="font-body text-xs text-error">
          {error}
        </p>
      )}
    </div>
  );
}
