"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useUiStore } from "@/stores/ui";
import {
  Play,
  Home,
  Film,
  Layers,
  Calendar,
  Users,
  Settings,
  Activity,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { listJobs, getAccounts, type AccountItem } from "@/lib/api";

const NAV_ITEMS = [
  { id: "studio",   icon: Home,     label: "Studio",   href: "/" },
  { id: "library",  icon: Film,     label: "Library",  href: "/library" },
  { id: "series",   icon: Layers,   label: "Series",   href: "/series" },
  { id: "schedule", icon: Calendar, label: "Schedule", href: "/schedule" },
  { id: "accounts", icon: Users,    label: "Accounts", href: "/accounts" },
  { id: "tasks",    icon: Activity, label: "Tasks",    href: "/tasks" },
  { id: "settings", icon: Settings, label: "Settings", href: "/settings" },
];

function isActive(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar() {
  const { sidebarExpanded, toggleSidebar } = useUiStore();
  const pathname = usePathname() || "/";

  const [activeCount, setActiveCount] = useState(0);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      try {
        const data = await listJobs();
        if (cancelled) return;
        const count = data.jobs.filter(
          (j) =>
            j.status === "running" ||
            j.status === "uploading" ||
            j.status === "queued" ||
            !!j.awaiting,
        ).length;
        setActiveCount(count);
      } catch {
        /* silent */
      } finally {
        if (!cancelled) timer = setTimeout(tick, 4000);
      }
    };
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  const [account, setAccount] = useState<AccountItem | null>(null);
  useEffect(() => {
    let cancelled = false;
    getAccounts()
      .then((accs) => {
        if (cancelled) return;
        if (accs.length > 0) setAccount(accs[0]);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const w = sidebarExpanded ? 240 : 64;
  const initials = (account?.nickname || account?.handle || "MP").slice(0, 2).toUpperCase();

  return (
    <motion.aside
      className="relative flex flex-col h-full z-10 shrink-0 overflow-hidden"
      style={{
        background: "var(--color-surf-1)",
        borderRight: "1px solid var(--color-hairline)",
      }}
      animate={{ width: w, minWidth: w }}
      transition={{ type: "tween", duration: 0.18, ease: [0.4, 0, 0.2, 1] }}
    >
      {/* Logo */}
      <div
        className={cn(
          "flex items-center h-14 border-b border-[var(--color-hairline)] shrink-0",
          sidebarExpanded ? "gap-[10px] px-4 justify-start" : "px-0 justify-center",
        )}
      >
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
          style={{
            background: "linear-gradient(135deg, #E8A24F 0%, #C47A28 100%)",
          }}
        >
          <Play size={14} className="text-white" strokeWidth={2.5} fill="white" />
        </div>
        {sidebarExpanded && (
          <span className="text-[13px] font-semibold text-[var(--color-text-primary)] whitespace-nowrap tracking-[-0.02em]">
            MoneyPrinter
          </span>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 p-2 flex flex-col gap-[2px]">
        {NAV_ITEMS.map((item) => {
          const active = isActive(item.href, pathname);
          const showBadge = item.id === "tasks" && activeCount > 0;
          return (
            <Tooltip key={item.id}>
              <TooltipTrigger asChild>
                <Link
                  href={item.href}
                  className={cn(
                    "flex items-center gap-[10px] rounded-lg transition-all duration-150 w-full relative",
                    sidebarExpanded ? "px-[10px] py-2 justify-start" : "py-2 justify-center",
                  )}
                  style={{
                    background: active ? "var(--color-amber-dim)" : "transparent",
                    color: active ? "var(--color-amber)" : "var(--color-text-secondary)",
                  }}
                  onMouseEnter={(e) => {
                    if (!active) {
                      e.currentTarget.style.background = "var(--color-surf-2)";
                      e.currentTarget.style.color = "var(--color-text-primary)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!active) {
                      e.currentTarget.style.background = "transparent";
                      e.currentTarget.style.color = "var(--color-text-secondary)";
                    }
                  }}
                >
                  {active && (
                    <span
                      className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 rounded-r"
                      style={{ background: "var(--color-amber)" }}
                    />
                  )}
                  <item.icon size={18} className="shrink-0" />
                  {sidebarExpanded && (
                    <span
                      className="text-[13px] whitespace-nowrap tracking-[-0.01em]"
                      style={{ fontWeight: active ? 500 : 400 }}
                    >
                      {item.label}
                    </span>
                  )}
                  {showBadge && (
                    <span
                      className={cn(
                        "ml-auto inline-flex items-center justify-center rounded-full text-[10px] font-semibold",
                        sidebarExpanded
                          ? "min-w-[20px] h-5 px-1.5"
                          : "absolute top-1 right-1 w-2 h-2 text-[0px]",
                      )}
                      style={{
                        background: "var(--color-amber)",
                        color: "#0B0B0D",
                      }}
                    >
                      {sidebarExpanded ? activeCount : ""}
                    </span>
                  )}
                </Link>
              </TooltipTrigger>
              {!sidebarExpanded && (
                <TooltipContent side="right">{item.label}</TooltipContent>
              )}
            </Tooltip>
          );
        })}
      </nav>

      {/* Account switcher */}
      {sidebarExpanded ? (
        <div
          className="flex items-center gap-2 px-3 py-3 border-t border-[var(--color-hairline)]"
        >
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0"
            style={{ background: "linear-gradient(135deg, #E8A24F 0%, #C47A28 100%)" }}
          >
            {initials}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[12px] font-medium text-[var(--color-text-primary)] leading-[1.3] truncate">
              {account?.nickname || "Operator"}
            </div>
            <div className="text-[11px] text-[var(--color-text-tertiary)] leading-[1.3] truncate">
              {account?.handle || account?.label || "MoneyPrinter"}
            </div>
          </div>
          <ChevronDown size={14} className="text-[var(--color-text-tertiary)]" />
        </div>
      ) : (
        <div className="flex justify-center py-3 border-t border-[var(--color-hairline)]">
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold text-white"
            style={{ background: "linear-gradient(135deg, #E8A24F 0%, #C47A28 100%)" }}
          >
            {initials}
          </div>
        </div>
      )}

      {/* Toggle */}
      <button
        className="flex items-center justify-center h-9 border-t border-[var(--color-hairline)] text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-secondary)]"
        onClick={toggleSidebar}
      >
        {sidebarExpanded ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
      </button>
    </motion.aside>
  );
}
