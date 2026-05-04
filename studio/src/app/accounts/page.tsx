"use client";

import { StudioShell } from "@/components/shell/StudioShell";
import { AccountsFrame } from "@/components/studio/AccountsFrame";

export default function AccountsPage() {
  return (
    <StudioShell title="Accounts" newHref="/shorts">
      <AccountsFrame />
    </StudioShell>
  );
}
