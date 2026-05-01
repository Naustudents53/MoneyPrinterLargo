"use client";

import { Sidebar } from "@/components/shell/Sidebar";
import { TopBar } from "@/components/shell/TopBar";
import { ContextPanel } from "@/components/shell/ContextPanel";
import { FloatingAIDirector } from "@/components/shell/FloatingAIDirector";
import { CommandPalette } from "@/components/shell/CommandPalette";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ProductionCanvas } from "@/components/studio/ProductionCanvas";

export function StudioShell({ type }: { type?: "short" | "long" | "recap" }) {
  return (
    <TooltipProvider>
      <div className="flex h-screen w-screen overflow-hidden bg-void relative">
        {/* Glow atmosférico ambiental */}
        <div className="absolute inset-0 pointer-events-none z-0">
          <div className="absolute top-0 left-1/4 w-[600px] h-[400px] rounded-full bg-accent-purple/5 blur-[120px]"
/>
          <div className="absolute bottom-0 right-1/4 w-[500px] h-[300px] rounded-full bg-accent-blue/4 blur-[100px]"
/>
        </div>

        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0 relative z-10">
          <TopBar />
          <ProductionCanvas type={type} />
        </div>
        <ContextPanel />
        <FloatingAIDirector />
        <CommandPalette />
      </div>
    </TooltipProvider>
  );
}
