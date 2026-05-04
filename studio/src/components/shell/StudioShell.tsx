"use client";

import { ReactNode } from "react";
import { Sidebar } from "@/components/shell/Sidebar";
import { TopBar } from "@/components/shell/TopBar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { CommandPalette } from "@/components/shell/CommandPalette";

export function StudioShell({
  children,
  title,
  newHref,
  showNew = true,
}: {
  children: ReactNode;
  title?: string;
  newHref?: string;
  showNew?: boolean;
}) {
  return (
    <TooltipProvider>
      <div
        className="flex h-screen w-screen overflow-hidden"
        style={{ background: "var(--color-base)", color: "var(--color-text-primary)" }}
      >
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <TopBar title={title} newHref={newHref} showNew={showNew} />
          <main className="flex-1 min-h-0 overflow-hidden flex flex-col">{children}</main>
        </div>
        <CommandPalette />
      </div>
    </TooltipProvider>
  );
}
