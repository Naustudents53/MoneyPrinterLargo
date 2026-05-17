import { useEffect, useState } from "react";
import { Moon, Sun, Monitor, Github, ExternalLink, Check } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useTheme } from "../ThemeProvider";
import { BackgroundJobs } from "../BackgroundJobs";
import { api, type SystemInfo } from "@/lib/api";
import { cn } from "@/lib/utils";

interface HeaderProps {
  title: string;
  description?: string;
  /** Optional small label rendered above the title in primary color (e.g. "· panel principal"). */
  eyebrow?: string;
  actions?: React.ReactNode;
}

export function Header({ title, description, eyebrow, actions }: HeaderProps) {
  const { theme, setTheme } = useTheme();
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [healthy, setHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .systemInfo()
      .then((d) => {
        if (!cancelled) {
          setInfo(d);
          setHealthy(true);
        }
      })
      .catch(() => !cancelled && setHealthy(false));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <header
      className="sticky top-0 z-30 min-h-[68px] flex items-center gap-3 sm:gap-[18px] px-3 sm:px-5 lg:px-7 bg-bg-raised/80 backdrop-blur-2xl shrink-0"
      style={{
        borderBottom: "1px solid hsl(var(--border) / .10)",
        boxShadow: "inset 0 -1px 0 hsl(var(--foreground) / .025)",
      }}
    >
      {/* Title block — eyebrow + title + description on a single baseline */}
      <div className="flex-1 min-w-0 flex flex-col gap-0.5">
        {eyebrow && <div className="eyebrow truncate">{eyebrow}</div>}
        <div className="flex items-baseline gap-3 min-w-0">
          <span className="font-display text-[17px] sm:text-[18px] font-semibold text-foreground whitespace-nowrap">
            {title}
          </span>
          {description && (
            <span className="hidden sm:inline text-[13px] text-muted-foreground truncate">
              {description}
            </span>
          )}
        </div>
      </div>

      {/* Slot for page-specific actions (e.g. "Generar" CTA) */}
      {actions}

      {/* Background jobs */}
      <BackgroundJobs />

      {/* System dropdown */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className="h-[36px] px-3 hidden sm:flex items-center gap-2 rounded-lg command-strip text-foreground text-[12px] transition-transform active:scale-[.98]"
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                healthy === false
                  ? "bg-destructive"
                  : healthy === true
                  ? "bg-success"
                  : "bg-muted-foreground"
              )}
              style={{
                boxShadow:
                  healthy === true
                    ? "0 0 0 3px hsl(var(--success) / .15)"
                    : healthy === false
                    ? "0 0 0 3px hsl(var(--destructive) / .15)"
                    : undefined,
              }}
            />
            <span className="font-mono">Sistema</span>
            <svg
              width={12}
              height={12}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              className="text-muted-foreground"
            >
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-[280px] p-3.5">
          <div className="flex items-center justify-between mb-3">
            <span className="eyebrow">Backend</span>
            <span
              className={cn(
                "inline-flex items-center gap-1.5 text-[10px] font-mono uppercase",
                healthy === false ? "text-destructive" : "text-success"
              )}
            >
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  healthy === false ? "bg-destructive" : "bg-success"
                )}
              />
              {healthy === false ? "offline" : "online"}
            </span>
          </div>
          {info ? (
            <div className="space-y-2 text-[12px]">
              <Row k="Versión API" v={`v${info.version}`} />
              <Row k="LLM" v={info.llm_provider} />
              <Row k="STT" v={info.stt_provider} />
              <Row k="Voz TTS" v={info.tts_voice} />
              <Row k="Aspect ratio" v={info.image_aspect_ratio} />
              <Row k="Headless" v={info.headless ? "true" : "false"} />
            </div>
          ) : (
            <div className="text-[12px] text-muted-foreground py-2">
              No se pudo conectar con el backend.
            </div>
          )}
          <div
            className="mt-3 pt-2"
            style={{ borderTop: "1px solid hsl(var(--border) / .07)" }}
          >
            <DropdownMenuItem asChild>
              <a
                href="http://127.0.0.1:8000/docs"
                target="_blank"
                rel="noreferrer"
                className="flex items-center justify-between gap-2"
              >
                <span>Abrir API docs</span>
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </DropdownMenuItem>
          </div>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Theme toggle */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className="w-[36px] h-[36px] flex items-center justify-center rounded-lg command-strip text-foreground transition-transform active:scale-[.96]"
            aria-label="Cambiar tema"
          >
            {theme === "dark" ? (
              <Moon className="h-4 w-4" strokeWidth={1.5} />
            ) : theme === "light" ? (
              <Sun className="h-4 w-4" strokeWidth={1.5} />
            ) : (
              <Monitor className="h-4 w-4" strokeWidth={1.5} />
            )}
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-40 p-1.5">
          <ThemeRow active={theme === "light"} onClick={() => setTheme("light")} icon={Sun} label="Claro" />
          <ThemeRow active={theme === "dark"} onClick={() => setTheme("dark")} icon={Moon} label="Oscuro" />
          <ThemeRow active={theme === "system"} onClick={() => setTheme("system")} icon={Monitor} label="Sistema" />
        </DropdownMenuContent>
      </DropdownMenu>

      {/* GitHub */}
      <Button
        asChild
        variant="ghost"
        size="icon"
        aria-label="GitHub"
        className="rounded-lg w-[34px] h-[34px]"
        style={{ border: "1px solid hsl(var(--border) / .10)" }}
      >
        <a
          href="https://github.com/anthropics/claude-code"
          target="_blank"
          rel="noreferrer"
          className="text-muted-foreground"
        >
          <Github className="h-4 w-4" strokeWidth={1.5} />
        </a>
      </Button>
    </header>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="font-mono text-[10.5px] uppercase text-muted-foreground">
        {k}
      </span>
      <span className="font-mono text-[11px] text-foreground truncate max-w-[150px]">{v}</span>
    </div>
  );
}

function ThemeRow({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof Sun;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-2.5 w-full px-2.5 py-1.5 rounded-md text-[12.5px] text-left",
        active ? "bg-surface text-foreground" : "text-muted-foreground hover:bg-surface hover:text-foreground"
      )}
    >
      <Icon className="h-3.5 w-3.5" strokeWidth={1.5} />
      <span className="flex-1">{label}</span>
      {active && <Check className="h-3.5 w-3.5 text-primary" strokeWidth={1.5} />}
    </button>
  );
}
