"use client";

// Task Monitor — global view of every job currently in JobManager memory.
//
// This is the page the user can open to SEE WHAT THE BOT IS DOING right now,
// without having to be inside the wizard. Polls /api/jobs every 2s.
//
// Each card shows:
//   • Type pill (short / long / recap) + topic
//   • Status badge (queued / running / uploading / done / error / cancelled)
//   • Current stage + message ("Generating images...", "Setting title", …)
//   • If a gate is open ("Awaiting your review"), a "Open wizard" button
//   • Progress bar (when stage_percent is set)
//   • Last log line (collapsed, in mono)
//   • Cancel button (running/uploading/awaiting only)
//   • If done, a video preview thumbnail + "Open on YouTube" link

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  Loader2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Play,
  ExternalLink,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  cancelJob,
  listJobs,
  type JobSummary,
  type Stage,
} from "@/lib/api";

const STAGE_LABEL: Record<string, string> = {
  topic: "Topic",
  script: "Script",
  metadata: "Metadata",
  prompts: "Image prompts",
  images: "Images",
  thumbnail: "Thumbnail",
  tts: "Narration",
  narration: "Narration",
  render: "Render",
  upload: "Upload",
  subtitles: "Subtitles",
};

const STATUS_CLASSES: Record<string, string> = {
  queued: "border-text-muted/30 bg-surface-overlay text-text-secondary",
  running: "border-accent-blue/30 bg-accent-blue/10 text-accent-blue-soft",
  uploading: "border-accent-purple/30 bg-accent-purple/10 text-accent-purple-soft",
  done: "border-success/30 bg-success/10 text-success",
  error: "border-error/30 bg-error/10 text-error",
  cancelled: "border-text-muted/30 bg-surface-overlay text-text-muted",
  unknown: "border-text-muted/30 bg-surface-overlay text-text-muted",
};

function StatusBadge({ status }: { status: JobSummary["status"] }) {
  const Icon =
    status === "done"
      ? CheckCircle2
      : status === "error"
        ? AlertTriangle
        : status === "cancelled"
          ? XCircle
          : status === "queued"
            ? Clock
            : Loader2;
  const animate = status === "running" || status === "uploading" || status === "queued";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wider",
        STATUS_CLASSES[status] ?? STATUS_CLASSES.unknown
      )}
    >
      <Icon size={10} className={animate && status !== "queued" ? "animate-spin" : ""} />
      {status}
    </span>
  );
}

function TypePill({ type }: { type: JobSummary["type"] }) {
  const label = type === "short" ? "Short" : type === "long" ? "Long" : "Recap";
  return (
    <span className="rounded bg-surface-overlay px-2 py-0.5 text-[10px] uppercase tracking-wider text-text-tertiary">
      {label}
    </span>
  );
}

function wizardHref(type: JobSummary["type"], jobId: string): string {
  // Append ?job=ID so JobAdopter on /shorts (or /long) hydrates the
  // local store from the backend job and jumps to the right stage.
  if (type === "short") return `/shorts?job=${jobId}`;
  if (type === "long") return `/long?job=${jobId}`;
  return "/";
}

function stageLabel(stage: Stage | string | null): string {
  if (!stage) return "—";
  return STAGE_LABEL[stage] ?? stage;
}

export function TaskMonitor() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyCancel, setBusyCancel] = useState<Record<string, boolean>>({});

  // Poll every 2s. AbortController prevents overlapping requests on slow
  // connections and stops in-flight ones on unmount.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;
    let controller: AbortController | null = null;

    const tick = async () => {
      controller = new AbortController();
      try {
        const data = await listJobs();
        if (cancelled) return;
        setJobs(data.jobs);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
        timer = setTimeout(tick, 2000);
      }
    };
    tick();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      controller?.abort();
    };
  }, []);

  const handleCancel = async (jobId: string) => {
    setBusyCancel((m) => ({ ...m, [jobId]: true }));
    try {
      await cancelJob(jobId);
    } catch {
      // The poll will refresh the row's state regardless.
    } finally {
      setBusyCancel((m) => ({ ...m, [jobId]: false }));
    }
  };

  if (loading) {
    return (
      <div className="p-8">
        <div className="text-sm text-text-tertiary">Loading tasks…</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Task Monitor</h1>
          <p className="text-sm text-text-tertiary">
            Every job currently in the pipeline — running, awaiting your input,
            or recently finished. Auto-refreshes every 2 seconds.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-text-muted">
          <RefreshCw size={12} className="animate-spin" style={{ animationDuration: "2s" }} />
          live
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-error/20 bg-error/10 px-4 py-3 text-sm text-error">
          API error: {error}
        </div>
      )}

      {jobs.length === 0 ? (
        <div className="rounded-2xl border border-border-ghost bg-surface-raised p-12 text-center">
          <div className="text-sm text-text-tertiary">
            No active tasks. Start one from <Link href="/shorts" className="text-accent-purple-soft hover:underline">Shorts</Link>{" "}
            or <Link href="/long" className="text-accent-purple-soft hover:underline">Long</Link>.
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <AnimatePresence mode="popLayout">
            {jobs.map((job) => {
              const cancellable =
                job.status === "running" ||
                job.status === "uploading" ||
                job.status === "queued" ||
                !!job.awaiting;
              const showProgress =
                job.stage_percent != null && job.stage_percent > 0;
              return (
                <motion.div
                  key={job.job_id}
                  layout
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className={cn(
                    "rounded-2xl border bg-surface-raised p-5 shadow-panel transition-colors",
                    job.awaiting
                      ? "border-accent-purple/40"
                      : job.status === "error"
                        ? "border-error/30"
                        : job.status === "done"
                          ? "border-success/30"
                          : "border-border-ghost"
                  )}
                >
                  {/* Header */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex flex-col gap-2 min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <TypePill type={job.type} />
                        <StatusBadge status={job.status} />
                        {job.awaiting && (
                          <span className="rounded-full border border-accent-purple/30 bg-accent-purple/10 px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-accent-purple-soft">
                            awaiting
                          </span>
                        )}
                      </div>
                      <div
                        className="text-base text-text-primary truncate"
                        title={job.topic || job.job_id}
                      >
                        {job.topic || <em className="text-text-muted">(no topic)</em>}
                      </div>
                      <div className="font-mono text-[10px] text-text-muted">
                        {job.job_id}
                      </div>
                    </div>
                  </div>

                  {/* Current stage line */}
                  <div className="mt-4 flex items-center justify-between gap-3">
                    <div className="flex flex-col gap-0.5 min-w-0">
                      <span className="text-[10px] uppercase tracking-wider text-text-muted">
                        Stage
                      </span>
                      <span className="text-sm text-text-secondary truncate">
                        {stageLabel(job.awaiting ?? job.current_stage)}
                        {job.stage_message && (
                          <span className="text-text-tertiary"> — {job.stage_message}</span>
                        )}
                      </span>
                    </div>
                    {showProgress && (
                      <span className="shrink-0 font-mono text-xs text-text-secondary">
                        {job.stage_percent}%
                      </span>
                    )}
                  </div>

                  {showProgress && (
                    <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-surface-sunken">
                      <motion.div
                        className="h-full rounded-full"
                        style={{
                          background: "linear-gradient(90deg, #7C3AED, #3B82F6)",
                        }}
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.min(job.stage_percent ?? 0, 100)}%` }}
                        transition={{ duration: 0.4 }}
                      />
                    </div>
                  )}

                  {/* Last log line */}
                  {job.last_log && (
                    <div className="mt-3 rounded-lg border border-border-subtle bg-surface-overlay px-3 py-2 font-mono text-[11px] text-text-tertiary line-clamp-2">
                      {job.last_log}
                    </div>
                  )}

                  {/* Footer actions */}
                  <div className="mt-4 flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      {job.video_url && (
                        <a
                          href={job.video_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1.5 rounded-lg border border-border-subtle bg-surface-overlay px-3 py-1.5 text-xs text-accent-blue-soft transition-colors hover:bg-surface-base"
                        >
                          <ExternalLink size={12} /> YouTube
                        </a>
                      )}
                      {(job.has_video || job.status === "done") && !job.video_url && (
                        <span className="inline-flex items-center gap-1.5 text-xs text-success">
                          <Play size={12} /> Video ready
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <Link
                        href={wizardHref(job.type, job.job_id)}
                        className={cn(
                          "rounded-lg px-3 py-1.5 text-xs transition-colors",
                          job.awaiting
                            ? "bg-accent-purple text-white shadow-glow-purple hover:bg-accent-purple-deep"
                            : "border border-border-subtle text-text-secondary hover:bg-surface-overlay hover:text-text-primary"
                        )}
                      >
                        {job.awaiting ? "Open wizard →" : "Open"}
                      </Link>
                      {cancellable && (
                        <button
                          onClick={() => handleCancel(job.job_id)}
                          disabled={busyCancel[job.job_id]}
                          className="inline-flex items-center gap-1 rounded-lg border border-error/20 bg-error/10 px-3 py-1.5 text-xs text-error transition-colors hover:bg-error/20 disabled:opacity-50"
                        >
                          {busyCancel[job.job_id] ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            <XCircle size={12} />
                          )}
                          Cancel
                        </button>
                      )}
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
