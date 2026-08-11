import { cn } from "@/lib/cn";

/**
 * Styled wrappers around real <table> elements -- not a data grid.
 *
 * Phase 4's vendor portal is table-heavy and needs a consistent look, not a
 * framework. Real table semantics also give screen readers row/column context
 * that a grid of <div>s cannot.
 *
 * The outer wrapper scrolls horizontally so a wide table never forces the page
 * itself sideways on a narrow screen -- part of Section 4.3's responsive floor.
 */

export function Table({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <div className="w-full overflow-x-auto">
      <table
        className={cn("w-full border-collapse font-body text-sm", className)}
        {...props}
      />
    </div>
  );
}

export function THead({ className, ...props }: React.ComponentProps<"thead">) {
  return <thead className={cn("border-b border-border", className)} {...props} />;
}

export function TBody(props: React.ComponentProps<"tbody">) {
  return <tbody {...props} />;
}

export function TR({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr className={cn("border-b border-border last:border-0", className)} {...props} />
  );
}

export function TH({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      // scope is what tells a screen reader which cells this header describes.
      scope="col"
      className={cn("px-3 py-2 text-left text-xs text-muted", className)}
      {...props}
    />
  );
}

export function TD({ className, ...props }: React.ComponentProps<"td">) {
  return <td className={cn("px-3 py-2 text-text", className)} {...props} />;
}
