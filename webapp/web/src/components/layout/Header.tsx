import { useEffect, useState } from "react";
import { Moon, Sun, Monitor, Github, ExternalLink, ServerCog } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useTheme } from "../ThemeProvider";
import { api, type SystemInfo } from "@/lib/api";

interface HeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}

export function Header({ title, description, actions }: HeaderProps) {
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
    <header className="sticky top-0 z-30 border-b border-border/60 bg-background/85 backdrop-blur-xl">
      <div className="h-16 px-6 flex items-center gap-4">
        <div className="flex-1 min-w-0">
          <h1 className="font-display text-lg sm:text-xl font-bold leading-none tracking-tight truncate">
            {title}
          </h1>
          {description && (
            <p className="text-xs sm:text-sm text-muted-foreground mt-1 truncate">{description}</p>
          )}
        </div>

        <div className="flex items-center gap-2">
          {actions}

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="gap-2">
                <ServerCog className="h-4 w-4" />
                <span className="hidden sm:inline">Sistema</span>
                <Badge
                  variant={healthy ? "success" : healthy === false ? "destructive" : "outline"}
                  className="ml-1"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
                  {healthy === null ? "…" : healthy ? "online" : "offline"}
                </Badge>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72">
              <DropdownMenuLabel>Estado del backend</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {info ? (
                <div className="px-2 py-1.5 text-xs space-y-1.5">
                  <Row k="Versión" v={info.version} />
                  <Row k="LLM" v={info.llm_provider} />
                  <Row k="STT" v={info.stt_provider} />
                  <Row k="Voz TTS" v={info.tts_voice} />
                  <Row k="Aspect ratio" v={info.image_aspect_ratio} />
                  <Row k="Headless" v={info.headless ? "sí" : "no"} />
                </div>
              ) : (
                <div className="px-2 py-3 text-xs text-muted-foreground">
                  No se pudo conectar con el backend.
                </div>
              )}
              <DropdownMenuSeparator />
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
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="icon" aria-label="Cambiar tema">
                {theme === "dark" ? (
                  <Moon className="h-4 w-4" />
                ) : theme === "light" ? (
                  <Sun className="h-4 w-4" />
                ) : (
                  <Monitor className="h-4 w-4" />
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setTheme("light")}>
                <Sun className="h-4 w-4" /> Light
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setTheme("dark")}>
                <Moon className="h-4 w-4" /> Dark
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setTheme("system")}>
                <Monitor className="h-4 w-4" /> Sistema
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <a
            href="https://github.com"
            target="_blank"
            rel="noreferrer"
            className="hidden sm:inline-flex"
          >
            <Button variant="ghost" size="icon" aria-label="GitHub">
              <Github className="h-4 w-4" />
            </Button>
          </a>
        </div>
      </div>
    </header>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-muted-foreground">{k}</span>
      <span className="font-mono text-foreground/90 truncate max-w-[150px]">{v}</span>
    </div>
  );
}
