import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Youtube,
  Twitter,
  ShoppingBag,
  Mail,
  Sparkles,
  Settings,
  Film,
  BookOpen,
  Image as ImageIcon,
  Activity,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { WordMark } from "../Logo";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

interface NavGroup {
  section: string;
  items: NavItem[];
}

const NAV: NavGroup[] = [
  {
    section: "Principal",
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
      { to: "/generate", label: "Generar contenido", icon: Sparkles },
    ],
  },
  {
    section: "Canales",
    items: [
      { to: "/channels", label: "Canales YouTube", icon: Youtube },
      { to: "/twitter", label: "Cuentas Twitter / X", icon: Twitter },
      { to: "/series", label: "Series", icon: BookOpen },
    ],
  },
  {
    section: "Otros flujos",
    items: [
      { to: "/affiliate", label: "Affiliate Marketing", icon: ShoppingBag },
      { to: "/outreach", label: "Outreach Local", icon: Mail },
      { to: "/storage", label: "Archivos de vídeo", icon: Film },
      { to: "/thumbnails", label: "Thumbnails", icon: ImageIcon },
    ],
  },
  {
    section: "Sistema",
    items: [
      { to: "/operations", label: "Operaciones", icon: Activity },
      { to: "/settings", label: "Configuración", icon: Settings },
    ],
  },
];

export function Sidebar() {
  return (
    <aside
      className="hidden lg:flex w-[276px] shrink-0 flex-col relative z-10"
      style={{
        borderRight: "1px solid hsl(var(--border) / .10)",
        background:
          "linear-gradient(180deg, hsl(var(--foreground) / .035), transparent 24%), hsl(var(--bg-raised) / .94)",
        boxShadow: "inset -1px 0 0 hsl(var(--foreground) / .025)",
      }}
    >
      {/* Brand */}
      <div
        className="h-[76px] px-5 flex items-center"
        style={{ borderBottom: "1px solid hsl(var(--border) / .10)" }}
      >
        <NavLink to="/" end aria-label="Ir al Dashboard" className="flex items-center min-w-0">
          <WordMark />
        </NavLink>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto scrollbar-thin px-3 py-4 flex flex-col gap-4">
        {NAV.map((group) => (
          <div key={group.section}>
            <div
              className="px-3 pb-2 pt-1 font-mono uppercase font-semibold text-[9.5px]"
              style={{
                letterSpacing: "0",
                color: "hsl(var(--muted-foreground) / .65)",
              }}
            >
              {group.section}
            </div>
            <ul className="flex flex-col gap-px">
              {group.items.map(({ to, label, icon: Icon, end }) => (
                <li key={to}>
                  <NavLink
                    to={to}
                    end={end ?? false}
                    className={({ isActive }) =>
                      cn(
                        "group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-normal transition-all duration-200 active:scale-[.99]",
                        isActive
                          ? "text-foreground font-medium"
                          : "text-muted-foreground hover:text-foreground"
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <span
                          aria-hidden
                          className={cn(
                            "absolute inset-0 rounded-lg transition-opacity",
                            isActive
                              ? "opacity-100"
                              : "opacity-0 group-hover:opacity-100"
                          )}
                          style={{
                            background: isActive
                              ? "linear-gradient(90deg, hsl(var(--primary) / .16), hsl(var(--surface) / .86))"
                              : "hsl(var(--surface) / .58)",
                            border: "1px solid hsl(var(--border) / .08)",
                          }}
                        />
                        <span
                          aria-hidden
                          className={cn("absolute left-[-12px] top-2 bottom-2 w-[3px] rounded-r transition-all", isActive ? "opacity-100 bg-primary" : "opacity-0")}
                        />
                        <Icon
                          className={cn(
                            "relative h-4 w-4 shrink-0 transition-colors",
                            isActive ? "text-primary" : "text-current"
                          )}
                          strokeWidth={1.5}
                        />
                        <span className="relative truncate flex-1">{label}</span>
                      </>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div
        className="m-3 mt-0 px-4 py-3.5 flex flex-col gap-2 command-strip rounded-xl"
      >
        <div className="font-display text-[12px] font-medium leading-snug text-foreground">
          Estudio listo para render.
        </div>
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-success animate-mpl-pulse" />
          <span className="font-mono text-[10px] text-muted-foreground">
            LOCAL PIPELINE
          </span>
        </div>
      </div>
    </aside>
  );
}

export function MobileNav() {
  const items = [
    NAV[0].items[0],
    NAV[0].items[1],
    NAV[1].items[0],
    NAV[2].items[3],
    NAV[3].items[1],
  ];

  return (
    <nav className="lg:hidden fixed inset-x-3 bottom-3 z-30 rounded-2xl glass px-2 py-2">
      <ul className="grid grid-cols-5 gap-1">
        {items.map(({ to, label, icon: Icon, end }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={end ?? false}
              className={({ isActive }) =>
                cn(
                  "flex h-[52px] flex-col items-center justify-center gap-1 rounded-xl text-[10px] transition-all active:scale-[.96]",
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-surface/70 hover:text-foreground",
                )
              }
            >
              <Icon className="h-4 w-4" strokeWidth={1.6} />
              <span className="max-w-full truncate px-1">{label.split(" ")[0]}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
