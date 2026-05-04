import { useEffect, useState } from "react";
import { Activity, CheckCircle2, Loader2, XCircle } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ProgressDialog } from "@/components/ProgressDialog";
import { api, type JobSummary } from "@/lib/api";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/lib/utils";

/**
 * Header widget that polls active+recent jobs and lets the user reattach to
 * any of them — useful when a generation modal was closed with "sigue en
 * background" and the user wants to check progress later.
 */
export function BackgroundJobs() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [open, setOpen] = useState(false);
  const [attaching, setAttaching] = useState<JobSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await api.listJobs(true);
        if (!cancelled) setJobs(data);
      } catch {
        /* silent — backend may be reloading */
      }
    };
    poll();
    const t = setInterval(poll, 3000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  const running = jobs.filter((j) => j.status === "running");
  const finished = jobs.filter((j) => j.status !== "running");

  return (
    <>
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            title="Trabajos en background"
          >
            <Activity className={cn("h-4 w-4", running.length > 0 && "text-primary animate-pulse")} />
            <span className="hidden sm:inline">Trabajos</span>
            <Badge
              variant={running.length > 0 ? "default" : "outline"}
              className="ml-1 font-mono"
            >
              {running.length}
            </Badge>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-[420px] max-w-[95vw]">
          <DropdownMenuLabel className="flex items-center justify-between">
            <span>Trabajos en background</span>
            <span className="text-xs font-normal text-muted-foreground">
              {running.length} corriendo · {finished.length} recientes
            </span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {jobs.length === 0 ? (
            <div className="px-3 py-6 text-xs text-muted-foreground text-center">
              No hay trabajos activos.
            </div>
          ) : (
            <div className="max-h-[60vh] overflow-auto scrollbar-thin">
              {jobs.map((j) => (
                <button
                  key={j.id}
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    setAttaching(j);
                  }}
                  className="w-full text-left px-3 py-2.5 hover:bg-muted/60 border-b border-border/40 last:border-0 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <JobStatusIcon status={j.status} />
                    <span className="text-sm font-medium truncate flex-1">{j.title}</span>
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {formatElapsed(j.elapsed)}
                    </Badge>
                  </div>
                  <div className="mt-1 ml-6 text-[11px] text-muted-foreground line-clamp-1 font-mono">
                    {j.last_line || "(sin output todavía)"}
                  </div>
                  <div className="mt-0.5 ml-6 text-[10px] text-muted-foreground/70">
                    {j.status === "running"
                      ? "ejecutando · click para reattach"
                      : `${j.status === "done" ? "completado" : "error"} · ${relativeTime(
                          j.finished_at || j.started_at
                        )}`}
                  </div>
                </button>
              ))}
            </div>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <ProgressDialog
        open={!!attaching}
        onOpenChange={(o) => !o && setAttaching(null)}
        title={attaching?.title || "Trabajo"}
        description="Reattach a un job en background — los logs se replayan desde el inicio."
        sseUrl={attaching ? api.jobStreamUrl(attaching.id) : null}
        channelId={attaching?.channel_id || undefined}
        kind={attaching?.kind || undefined}
      />
    </>
  );
}

function JobStatusIcon({ status }: { status: JobSummary["status"] }) {
  if (status === "running") return <Loader2 className="h-4 w-4 animate-spin text-primary shrink-0" />;
  if (status === "done") return <CheckCircle2 className="h-4 w-4 text-success shrink-0" />;
  return <XCircle className="h-4 w-4 text-destructive shrink-0" />;
}

function formatElapsed(s: number) {
  if (s < 60) return `${s.toFixed(0)}s`;
  const m = Math.floor(s / 60);
  const r = Math.floor(s - m * 60);
  return `${m}m${r}s`;
}
