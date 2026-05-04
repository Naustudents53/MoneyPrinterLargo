"use client";

import { StudioShell } from "@/components/shell/StudioShell";
import { SettingsFrame } from "@/components/studio/SettingsFrame";

export default function SettingsPage() {
  return (
    <StudioShell title="Settings" newHref="/shorts">
      <SettingsFrame />
    </StudioShell>
  );
}
