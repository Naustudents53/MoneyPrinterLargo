"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

function Dialog({ ...props }: React.ComponentProps<typeof DialogPrimitive.Root>) { return <DialogPrimitive.Root {...props} />; }
function DialogTrigger({ ...props }: React.ComponentProps<typeof DialogPrimitive.Trigger>) { return <DialogPrimitive.Trigger asChild {...props} />; }
function DialogPortal({ ...props }: React.ComponentProps<typeof DialogPrimitive.Portal>) { return <DialogPrimitive.Portal {...props} />; }
function DialogOverlay({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Overlay>) {
  return <DialogPrimitive.Overlay className={cn("fixed inset-0 z-50 bg-black/60 backdrop-blur-sm", className)} {...props} />;
}
function DialogContent({ className, children, ...props }: React.ComponentProps<typeof DialogPrimitive.Content>) {
  return (
    <DialogPortal><DialogOverlay />
      <DialogPrimitive.Content className={cn("fixed left-[50%] top-[50%] z-50 w-full max-w-lg translate-x-[-50%] translate-y-[-50%] rounded-2xl border border-border-default bg-surface-overlay p-6 shadow-xl", className)} {...props}>
        {children}
        <DialogPrimitive.Close className="absolute right-4 top-4 rounded-lg opacity-70 hover:opacity-100 transition-opacity"><X size={16} className="text-text-secondary" /></DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPortal>
  );
}
function DialogHeader({ className, ...props }: React.ComponentProps<"div">) { return <div className={cn("flex flex-col space-y-1.5 text-left", className)} {...props} />; }
function DialogTitle({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Title>) { return <DialogPrimitive.Title className={cn("text-lg font-semibold text-text-primary", className)} {...props} />; }
function DialogDescription({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Description>) { return <DialogPrimitive.Description className={cn("text-sm text-text-secondary", className)} {...props} />; }

export { Dialog, DialogPortal, DialogOverlay, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogDescription };
