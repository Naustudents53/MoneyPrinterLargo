"use client";

import { create } from "zustand";

interface UiState {
  sidebarExpanded: boolean;
  contextPanelOpen: boolean;
  commandPaletteOpen: boolean;
  toggleSidebar: () => void;
  setSidebarExpanded: (v: boolean) => void;
  toggleContextPanel: () => void;
  openCommandPalette: () => void;
  closeCommandPalette: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  sidebarExpanded: true,
  contextPanelOpen: true,
  commandPaletteOpen: false,
  toggleSidebar: () => set((s) => ({ sidebarExpanded: !s.sidebarExpanded })),
  setSidebarExpanded: (v) => set({ sidebarExpanded: v }),
  toggleContextPanel: () => set((s) => ({ contextPanelOpen: !s.contextPanelOpen })),
  openCommandPalette: () => set({ commandPaletteOpen: true }),
  closeCommandPalette: () => set({ commandPaletteOpen: false }),
}));
