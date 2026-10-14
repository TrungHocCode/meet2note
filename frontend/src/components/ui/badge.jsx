import { Slot } from "radix-ui"
import { cva } from "class-variance-authority"

import { cn } from "../../lib/utils.js"

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground",
        secondary: "bg-muted text-muted-foreground",
        outline: "border bg-card text-foreground",
        destructive: "bg-conf-red-bg text-conf-red",
        "conf-red": "bg-conf-red-bg text-conf-red",
        "conf-amber": "bg-conf-amber-bg text-conf-amber",
        "conf-green": "bg-conf-green-bg text-conf-green",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({ className, variant, asChild = false, ...props }) {
  const Comp = asChild ? Slot.Root : "span"
  return (
    <Comp data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
