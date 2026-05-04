"use client";

import { StudioShell } from "@/components/shell/StudioShell";
import { HomeFrame } from "@/components/studio/HomeFrame";

export default function Home() {
  return (
    <StudioShell title="Studio" newHref="/shorts">
      <HomeFrame />
    </StudioShell>
  );
}
