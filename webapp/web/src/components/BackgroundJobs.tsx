import { useEffect, useState } from "react";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ProgressDialog } from "@/components/ProgressDialog";
import { api, type JobSummary } from "@/lib/api";
import { cn, relativeTime } from "@/lib/utils";

/**
 * Compact "N jobs" pill that lives in the header. Polls /api/jobs every 3s,
 * lets the user reattach to any job via ProgressDialog. Visible only when at
 * least one job is running.
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

  if (running.length === 0 && finished.length === 0) return null;

  return (
    <>
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <button
            className="h-[34px] px-2.5 flex items-center gap-2 rounded-lg bg-surface text-foreground text-[12px]"
            style={{ border: "1px solid hsl(var(--border) / .07)" }}
            title="Trabajos en background"
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                running.length > 0 ? "bg-warning animate-mpl-pulse" : "bg-muted-foreground"
              )}
              style={{
                boxShadow:
                  running.length > 0
                    ? "0 0 0 4px hsl(var(--warning) / .15)"
                    : undefined,
              }}
            />
            <span className="font-mono text-[11px]">
              {running.length} job{running.length !== 1 ? "s" : ""}
            </span>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-[420px] max-w-[95vw]">
          <DropdownMenuLabel className="flex items-center justify-between">
            <span>Trabajos en background</span>
            <span className="text-[10px] font-normal text-muted-foreground font-mono uppercase tracking-wider">
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
                  className="w-full text-left px-3 py-2.5 hover:bg-surface transition-colors"
                  style={{ borderBottom: "1px solid hsl(var(--border) / .04)" }}
                >
                  <div className="flex items-center gap-2">
                    <JobStatusIcon status={j.status} />
                    <span className="text-sm font-medium truncate flex-1">{j.title}</span>
                    <span
                      className="font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded"
                      style={{
                        border: "1px solid hsl(var(--border) / .12)",
                        color: "hsl(var(--muted-foreground))",
                      }}
                    >
                      {formatElapsed(j.elapsed)}
                    </span>
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
        description="Reattach a un job en background — los logs se reproducen desde el inicio."
        sseUrl={attaching ? api.jobStreamUrl(attaching.id) : null}
        channelId={attaching?.channel_id || undefined}
        kind={attaching?.kind || undefined}
      />
    </>
  );
}

/**
 * BackgroundJobsBar — strip below the header showing running jobs with a
 * fake but expressive "progress" indicator (we don't have real progress
 * percentages from the API, so we render an indeterminate brand-gradient bar
 * + elapsed timer instead). Click any job to reattach.
 */
export function BackgroundJobsBar() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [attaching, setAttaching] = useState<JobSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await api.listJobs(false);
        if (!cancelled) setJobs(data);
      } catch {
        /* silent */
      }
    };
    poll();
    const t = setInterval(poll, 2500);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  const running = jobs.filter((j) => j.status === "running");
  if (running.length === 0) return null;

  return (
    <>
      <div
        className="bg-bg-raised/70 backdrop-blur-md px-7 py-2 flex items-center gap-3.5 shrink-0"
        style={{ borderBottom: "1px solid hsl(var(--border) / .07)" }}
      >
        <span className="eyebrow text-muted-foreground">Jobs activos</span>
        <div className="flex items-center gap-2.5 flex-1 overflow-x-auto scrollbar-thin">
          {running.map((j) => (
            <button
              key={j.id}
              onClick={() => setAttaching(j)}
              className="h-[30px] px-3 flex items-center gap-2.5 rounded-lg bg-surface text-foreground text-[12px] shrink-0 hover:bg-surface-up transition-colors"
              style={{ border: "1px solid hsl(var(--border) / .07)" }}
            >
              <span
                className="h-1.5 w-1.5 rounded-full bg-warning animate-mpl-pulse"
                style={{ boxShadow: "0 0 0 3px hsl(var(--warning) / .15)" }}
              />
              <span className="font-medium max-w-[200px] truncate">{j.title}</span>
              <span
                className="w-20 h-1 rounded overflow-hidden bg-surface-up relative"
                aria-hidden
              >
                <span
                  className="absolute inset-y-0 bg-brand-gradient"
                  style={{
                    width: "60%",
                    animation: "mpl-shimmer 2s linear infinite",
                  }}
                />
              </span>
              <span className="font-mono text-[11px] text-muted-foreground">
                · {formatElapsed(j.elapsed)}
              </span>
            </button>
          ))}
        </div>
      </div>

      <ProgressDialog
        open={!!attaching}
        onOpenChange={(o) => !o && setAttaching(null)}
        title={attaching?.title || "Trabajo"}
        description="Reattach a un job en background — los logs se reproducen desde el inicio."
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
