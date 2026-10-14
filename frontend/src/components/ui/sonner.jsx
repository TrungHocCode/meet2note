import { Toaster as Sonner } from "sonner"

function Toaster({ ...props }) {
  return (
    <Sonner
      data-slot="toaster"
      position="bottom-right"
      toastOptions={{
        classNames: {
          toast:
            "rounded-lg border bg-card text-foreground shadow-drawer",
          description: "text-muted-foreground",
          actionButton: "bg-primary text-primary-foreground",
          cancelButton: "bg-muted text-muted-foreground",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
export { toast } from "sonner"
