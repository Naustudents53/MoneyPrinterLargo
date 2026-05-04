"use client";

import { StudioShell } from "@/components/shell/StudioShell";
import { LibraryFrame } from "@/components/studio/LibraryFrame";

export default function LibraryPage() {
  return (
    <StudioShell title="Library" newHref="/shorts">
      <LibraryFrame />
    </StudioShell>
  );
}
