import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { BackgroundJobsBar } from "../BackgroundJobs";

export function AppShell() {
  return (
    <div className="min-h-screen flex bg-background text-foreground">
      <Sidebar />
      <div className="flex-1 min-w-0 flex flex-col">
        <Outlet />
      </div>
    </div>
  );
}

/**
 * PageShell — main scroll container under the header. The jobs bar slots
 * between the page header (rendered by each page) and the scrollable
 * content. We render it inside PageShell so every page automatically
 * inherits it without each one having to import it.
 */
export function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <BackgroundJobsBar />
      <main className="flex-1 px-7 py-7 mesh-bg overflow-auto scrollbar-thin animate-fade-in">
        <div className="max-w-[90rem] mx-auto space-y-4">{children}</div>
      </main>
    </>
  );
}
