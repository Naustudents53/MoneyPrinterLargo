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
      className="hidden lg:flex w-64 shrink-0 flex-col bg-bg-raised relative z-10"
      style={{ borderRight: "1px solid hsl(var(--border) / .07)" }}
    >
      {/* Brand */}
      <div
        className="h-16 px-[18px] flex items-center"
        style={{ borderBottom: "1px solid hsl(var(--border) / .07)" }}
      >
        <NavLink to="/" end aria-label="Ir al Dashboard" className="flex items-center min-w-0">
          <WordMark />
        </NavLink>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto scrollbar-thin px-2.5 py-3.5 flex flex-col gap-3.5">
        {NAV.map((group) => (
          <div key={group.section}>
            <div
              className="px-2.5 pb-2 pt-1 font-mono uppercase font-semibold text-[9.5px]"
              style={{
                letterSpacing: "0.20em",
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
                        "group relative flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13px] font-normal transition-all",
                        isActive
                          ? "bg-surface text-foreground font-medium"
                          : "text-muted-foreground hover:bg-surface hover:text-foreground"
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <span
                          aria-hidden
                          className={cn(
                            "absolute left-[-10px] top-1.5 bottom-1.5 w-[3px] rounded-r transition-all",
                            isActive
                              ? "opacity-100 bg-brand-gradient shadow-[0_0_12px_hsl(var(--primary)/.55)]"
                              : "opacity-0"
                          )}
                        />
                        <Icon
                          className={cn(
                            "h-4 w-4 shrink-0 transition-colors",
                            isActive ? "text-primary" : "text-current"
                          )}
                          strokeWidth={1.5}
                        />
                        <span className="truncate flex-1">{label}</span>
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
        className="px-[18px] py-3.5 flex flex-col gap-1.5"
        style={{ borderTop: "1px solid hsl(var(--border) / .07)" }}
      >
        <div className="font-display text-[12px] font-medium leading-snug tracking-tight">
          <span className="brand-text">Imprime largo,</span>
          <span className="text-muted-foreground"> edita poco.</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className="font-mono text-[9.5px] font-semibold px-1.5 py-px rounded border"
            style={{
              borderColor: "hsl(var(--border) / .12)",
              background: "hsl(var(--surface))",
              color: "hsl(var(--muted-foreground))",
            }}
          >
            MPL
          </span>
          <span className="font-mono text-[10px] text-muted-foreground tracking-wider">
            v1.0.0
          </span>
        </div>
      </div>
    </aside>
  );
}
