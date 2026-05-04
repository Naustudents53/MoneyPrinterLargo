"use client";

import { StudioShell } from "@/components/shell/StudioShell";
import { ScheduleFrame } from "@/components/studio/ScheduleFrame";

export default function SchedulePage() {
  return (
    <StudioShell title="Schedule" newHref="/shorts">
      <ScheduleFrame />
    </StudioShell>
  );
}
