"use client";

import { StudioShell } from "@/components/shell/StudioShell";
import { ProductionCanvas } from "@/components/studio/ProductionCanvas";

export default function LongPage() {
  return (
    <StudioShell title="New Long-Form" newHref="/long" showNew={false}>
      <ProductionCanvas type="long" />
    </StudioShell>
  );
}
