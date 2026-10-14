import { ToggleGroup as ToggleGroupPrimitive } from "radix-ui"
import { cva } from "class-variance-authority"

import { cn } from "../../lib/utils.js"

const toggleGroupItemVariants = cva(
  "inline-flex min-h-8 flex-1 items-center justify-center gap-1 rounded-md px-2 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 data-[state=on]:bg-card data-[state=on]:text-foreground data-[state=on]:shadow-sm data-[state=off]:text-muted-foreground data-[state=off]:hover:text-foreground",
)

function ToggleGroup({ className, ...props }) {
  return (
    <ToggleGroupPrimitive.Root
      data-slot="toggle-group"
      className={cn("flex items-center gap-1 rounded-lg bg-muted p-1", className)}
      {...props}
    />
  )
}

function ToggleGroupItem({ className, ...props }) {
  return (
    <ToggleGroupPrimitive.Item
      data-slot="toggle-group-item"
      className={cn(toggleGroupItemVariants(), className)}
      {...props}
    />
  )
}

export { ToggleGroup, ToggleGroupItem }
