import { cva } from "class-variance-authority"

import { cn } from "../../lib/utils.js"

const alertVariants = cva(
  "rounded-lg border px-4 py-3 text-sm [&>svg]:size-4",
  {
    variants: {
      variant: {
        default: "border bg-card text-foreground",
        warn: "border-conf-amber/40 bg-conf-amber-bg text-conf-amber",
        ok: "border-conf-green/40 bg-ok-bg text-conf-green",
        destructive: "border-destructive/40 bg-conf-red-bg text-destructive",
        info: "border-sky-200 bg-info-bg text-sky-900",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Alert({ className, variant, ...props }) {
  return <div data-slot="alert" role="alert" className={cn(alertVariants({ variant }), className)} {...props} />
}

function AlertTitle({ className, ...props }) {
  return <h5 data-slot="alert-title" className={cn("font-semibold", className)} {...props} />
}

function AlertDescription({ className, ...props }) {
  return <div data-slot="alert-description" className={cn("text-sm opacity-90", className)} {...props} />
}

export { Alert, AlertTitle, AlertDescription, alertVariants }
