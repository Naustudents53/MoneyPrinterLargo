"use client";

import { StudioShell } from "@/components/shell/StudioShell";
import { ProductionCanvas } from "@/components/studio/ProductionCanvas";

export default function RecapPage() {
  return (
    <StudioShell title="New Movie Recap" newHref="/recap" showNew={false}>
      <ProductionCanvas type="recap" />
    </StudioShell>
  );
}
