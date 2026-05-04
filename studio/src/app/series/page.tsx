"use client";

import { StudioShell } from "@/components/shell/StudioShell";
import { SeriesFrame } from "@/components/studio/SeriesFrame";

export default function SeriesPage() {
  return (
    <StudioShell title="Series" newHref="/shorts">
      <SeriesFrame />
    </StudioShell>
  );
}
