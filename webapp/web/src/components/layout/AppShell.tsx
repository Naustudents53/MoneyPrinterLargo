import { Outlet } from "react-router-dom";
import { MobileNav, Sidebar } from "./Sidebar";
import { BackgroundJobsBar } from "../BackgroundJobs";

export function AppShell() {
  return (
    <div className="studio-noise h-[100dvh] flex bg-background text-foreground overflow-hidden">
      <Sidebar />
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
        <Outlet />
      </div>
      <MobileNav />
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
      <main className="flex-1 px-3 pb-24 pt-3 sm:px-5 sm:pt-5 lg:px-7 lg:py-7 mesh-bg overflow-auto scrollbar-thin animate-fade-in">
        <div className="max-w-[92rem] mx-auto space-y-4 lg:space-y-5 reveal-in">{children}</div>
      </main>
    </>
  );
}
