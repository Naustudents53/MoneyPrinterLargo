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
      { to: "/storage", label: "Archivos de video", icon: Film },
      { to: "/thumbnails", label: "Thumbnails", icon: ImageIcon },
    ],
  },
  {
    section: "Sistema",
    items: [{ to: "/settings", label: "Configuración", icon: Settings }],
  },
];

export function Sidebar() {
  return (
    <aside className="hidden lg:flex w-64 shrink-0 flex-col border-r border-border/70 bg-card/55 backdrop-blur-xl">
      <NavLink
        to="/"
        end
        className="h-16 px-5 flex items-center border-b border-border/70 hover:bg-muted/40 transition-colors"
        aria-label="Ir al Dashboard"
      >
        <WordMark />
      </NavLink>
      <nav className="flex-1 overflow-y-auto scrollbar-thin px-3 py-4 space-y-5">
        {NAV.map((group) => (
          <div key={group.section}>
            <div className="px-3 mb-2 eyebrow text-muted-foreground/70">
              {group.section}
            </div>
            <ul className="space-y-0.5">
              {group.items.map(({ to, label, icon: Icon, end }) => (
                <li key={to}>
                  <NavLink
                    to={to}
                    end={end ?? false}
                    className={({ isActive }) =>
                      cn(
                        "group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-all",
                        isActive
                          ? "bg-gradient-to-r from-primary/15 via-primary/8 to-transparent text-foreground shadow-[inset_0_0_0_1px_hsl(var(--primary)/.2)]"
                          : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <span
                          aria-hidden
                          className={cn(
                            "absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-r-full transition-all",
                            isActive
                              ? "bg-primary opacity-100 shadow-[0_0_12px_hsl(var(--primary)/.6)]"
                              : "bg-primary opacity-0 group-hover:opacity-40"
                          )}
                        />
                        <Icon
                          className={cn(
                            "h-4 w-4 shrink-0 transition-colors",
                            isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                          )}
                        />
                        <span className="truncate">{label}</span>
                      </>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      <div className="px-4 py-4 border-t border-border/70 text-[11px] text-muted-foreground space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="font-mono tracking-[0.24em]">v1.0.0</span>
          <span className="font-mono tracking-[0.32em] text-primary/80">MPL</span>
        </div>
        <div className="brand-text font-display font-semibold tracking-tight">
          Imprime largo, edita poco.
        </div>
      </div>
    </aside>
  );
}
