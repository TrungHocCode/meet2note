import { Slot } from "radix-ui"
import { cva } from "class-variance-authority"

import { cn } from "../../lib/utils.js"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl px-4 py-2 text-sm font-semibold transition-colors duration-150 ease-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:cursor-not-allowed [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:brightness-95 active:brightness-90 disabled:bg-muted disabled:text-muted-foreground",
        destructive:
          "border border-destructive/30 bg-card text-destructive hover:bg-conf-red-bg active:border-destructive disabled:bg-muted disabled:text-muted-foreground disabled:border-border",
        outline:
          "border bg-card text-foreground hover:bg-muted active:bg-muted disabled:bg-muted disabled:text-muted-foreground",
        ghost: "text-foreground hover:bg-muted active:bg-muted",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "min-h-9",
        xs: "min-h-7 rounded-md px-2 py-1 text-xs gap-1 [&_svg]:size-3.5",
        sm: "min-h-8 rounded-lg px-2.5 text-xs gap-1.5 [&_svg]:size-3.5",
        lg: "min-h-10 px-6",
        icon: "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({ className, variant, size, asChild = false, ...props }) {
  const Comp = asChild ? Slot.Root : "button"
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
