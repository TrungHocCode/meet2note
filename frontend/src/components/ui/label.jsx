import { Label as LabelPrimitive } from "radix-ui"

import { cn } from "../../lib/utils.js"

function Label({ className, ...props }) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn("text-xs font-medium text-foreground", className)}
      {...props}
    />
  )
}

export { Label }
