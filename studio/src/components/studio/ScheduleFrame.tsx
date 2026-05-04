"use client";

import { useEffect, useState } from "react";
import { Calendar } from "lucide-react";
import { listJobs, type JobSummary } from "@/lib/api";
import { StatusPill } from "@/components/ui/status-pill";

export function ScheduleFrame() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      try {
        const data = await listJobs();
        if (cancelled) return;
        setJobs(data.jobs);
      } catch {
        /* ignore */
      } finally {
        if (!cancelled) timer = setTimeout(tick, 5000);
      }
    };
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  const upcoming = jobs.filter(
    (j) => j.status === "queued" || !!j.awaiting,
  );
  const inFlight = jobs.filter(
    (j) => j.status === "running" || j.status === "uploading",
  );

  return (
    <div className="flex-1 overflow-auto p-8 flex flex-col gap-10">
      <Section title="In flight" icon emptyText="No active jobs.">
        {inFlight.length > 0 &&
          inFlight.map((j) => <JobRow key={j.job_id} job={j} status="running" />)}
      </Section>

      <Section title="Awaiting / queued" icon emptyText="The queue is clear.">
        {upcoming.length > 0 &&
          upcoming.map((j) => (
            <JobRow key={j.job_id} job={j} status={j.awaiting ? "pending" : "queued"} />
          ))}
      </Section>

      <Section
        title="Recurring (config.json)"
        emptyText="No recurring jobs configured. Schedules live in config.json under cron entries."
      >
        {/* Placeholder until we expose config.json schedule via the API */}
      </Section>
    </div>
  );
}

function Section({
  title,
  emptyText,
  icon,
  children,
}: {
  title: string;
  emptyText: string;
  icon?: boolean;
  children?: React.ReactNode;
}) {
  const isEmpty = !children || (Array.isArray(children) && children.length === 0);
  return (
    <section>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-[12px] font-semibold tracking-[0.08em] uppercase text-[var(--color-text-tertiary)]">
          {title}
        </h2>
        {icon && <Calendar size={14} className="text-[var(--color-text-tertiary)]" />}
      </div>
      {isEmpty ? (
        <div
          className="rounded-[12px] py-8 text-center text-[12px] text-[var(--color-text-tertiary)]"
          style={{
            background: "var(--color-surf-1)",
            border: "1px solid var(--color-hairline)",
          }}
        >
          {emptyText}
        </div>
      ) : (
        <div className="flex flex-col gap-2">{children}</div>
      )}
    </section>
  );
}

function JobRow({
  job,
  status,
}: {
  job: JobSummary;
  status: Parameters<typeof StatusPill>[0]["status"];
}) {
  return (
    <a
      href={`/tasks?job=${job.job_id}`}
      className="flex items-center gap-3 rounded-md px-4 py-3 transition-colors duration-100"
      style={{
        background: "var(--color-surf-2)",
        border: "1px solid var(--color-hairline)",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-surf-3)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "var(--color-surf-2)")}
    >
      <span className="font-mono text-[11px] text-[var(--color-amber)] w-[60px] shrink-0 truncate">
        {job.created_at ? new Date(job.created_at).toLocaleTimeString() : "—"}
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-[13px] font-medium text-[var(--color-text-primary)] truncate">
          {job.topic || job.job_id.slice(0, 8)}
        </div>
        <div className="text-[11px] text-[var(--color-text-tertiary)] truncate">
          {job.account_id || "—"} · {job.type}
          {job.stage_message ? ` · ${job.stage_message}` : ""}
        </div>
      </div>
      <StatusPill status={status} size="xs" />
    </a>
  );
}
