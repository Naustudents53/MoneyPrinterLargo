"use client";

import { StudioShell } from "@/components/shell/StudioShell";
import { ProductionCanvas } from "@/components/studio/ProductionCanvas";

export default function ShortsPage() {
  return (
    <StudioShell title="New Short" newHref="/shorts" showNew={false}>
      <ProductionCanvas type="short" />
    </StudioShell>
  );
}
