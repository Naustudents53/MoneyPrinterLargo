import { TaskMonitor } from "@/components/studio/TaskMonitor";
import { Sidebar } from "@/components/shell/Sidebar";
import { TopBar } from "@/components/shell/TopBar";
import { TooltipProvider } from "@/components/ui/tooltip";

export default function TasksPage() {
  return (
    <TooltipProvider>
      <div className="flex h-screen w-screen overflow-hidden bg-void relative">
        <div className="absolute inset-0 pointer-events-none z-0">
          <div className="absolute top-0 left-1/4 w-[600px] h-[400px] rounded-full bg-accent-purple/5 blur-[120px]" />
          <div className="absolute bottom-0 right-1/4 w-[500px] h-[300px] rounded-full bg-accent-blue/4 blur-[100px]" />
        </div>

        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0 relative z-10">
          <TopBar />
          <div className="flex-1 overflow-auto">
            <TaskMonitor />
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
