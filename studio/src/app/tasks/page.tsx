"use client";

import { StudioShell } from "@/components/shell/StudioShell";
import { TaskMonitor } from "@/components/studio/TaskMonitor";

export default function TasksPage() {
  return (
    <StudioShell title="Tasks" newHref="/shorts">
      <div className="flex-1 overflow-auto">
        <TaskMonitor />
      </div>
    </StudioShell>
  );
}
