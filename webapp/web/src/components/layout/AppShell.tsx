import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  return (
    <div className="min-h-screen flex bg-background">
      <Sidebar />
      <div className="flex-1 min-w-0 flex flex-col">
        <Outlet />
      </div>
    </div>
  );
}

export function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex-1 px-6 py-6 lg:px-8 lg:py-8 mesh-bg overflow-auto scrollbar-thin animate-fade-in">
      <div className="max-w-[96rem] mx-auto space-y-6">{children}</div>
    </main>
  );
}
