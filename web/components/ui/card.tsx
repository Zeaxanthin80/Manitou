import { cn } from "@/lib/cn";

/**
 * Surface container. Composed rather than configured -- Card/CardHeader/CardBody
 * as separate pieces means the storefront and the denser admin screens can vary
 * the internals without either growing a pile of boolean props.
 */

export function Card({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-md border border-border bg-surface shadow-sm",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("border-b border-border px-4 py-3", className)}
      {...props}
    />
  );
}

export function CardBody({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("p-4", className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.ComponentProps<"h3">) {
  return (
    <h3
      className={cn("font-display text-lg text-text", className)}
      {...props}
    />
  );
}
