"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Zap,
  Film,
  Hash,
  ChevronRight,
  Calendar,
  Database,
  Trash2,
} from "lucide-react";
import { VideoTile, type VideoTileData } from "@/components/ui/video-tile";
import { StatusPill } from "@/components/ui/status-pill";
import { listJobs, type JobSummary } from "@/lib/api";

const MAKE_CARDS = [
  {
    id: "short",
    label: "YouTube Short",
    sub: "Vertical · ~45s · AI images + TTS",
    icon: Zap,
    color: "#E8A24F",
    bg: "#2A1F0D",
    href: "/shorts",
  },
  {
    id: "long",
    label: "Long-Form Video",
    sub: "16:9 · 15–20 min · Series",
    icon: Film,
    color: "#60A5FA",
    bg: "#0D1A2A",
    href: "/long",
  },
  {
    id: "tweet",
    label: "Tweet / Affiliate",
    sub: "Twitter Bot · X auto-post",
    icon: Hash,
    color: "#4ADE80",
    bg: "#0D2A1A",
    href: "/tweet",
  },
];

function relTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "—";
  const ms = Date.now() - t;
  const m = Math.round(ms / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return `${d}d ago`;
}

function jobToTile(job: JobSummary): VideoTileData {
  const isLong = job.type === "long";
  const status: VideoTileData["status"] =
    job.status === "done" && job.video_url
      ? "uploaded"
      : job.status === "running" || job.status === "uploading"
      ? "rendering"
      : job.status === "error"
      ? "failed"
      : job.status === "cancelled"
      ? "draft"
      : job.status === "queued" || job.awaiting
      ? "pending"
      : "draft";
  return {
    id: job.job_id,
    title: job.topic || `Job ${job.job_id.slice(0, 8)}`,
    duration: isLong ? "~18:00" : "~0:45",
    status,
    platform: "youtube",
    aspect: isLong ? "16:9" : "9:16",
    thumb: isLong ? "#1A3D2A" : "#3D2A1A",
    views: null,
  };
}

export function HomeFrame() {
  const router = useRouter();
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [stats, setStats] = useState({
    total: 0,
    week: 0,
    rendering: 0,
    failed: 0,
  });

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      try {
        const data = await listJobs();
        if (cancelled) return;
        setJobs(data.jobs);
        const now = Date.now();
        const weekMs = 7 * 24 * 3600 * 1000;
        const week = data.jobs.filter(
          (j) => j.created_at && now - new Date(j.created_at).getTime() < weekMs,
        ).length;
        setStats({
          total: data.jobs.filter((j) => j.status === "done" && j.has_video).length,
          week,
          rendering: data.jobs.filter(
            (j) => j.status === "running" || j.status === "uploading",
          ).length,
          failed: data.jobs.filter((j) => j.status === "error").length,
        });
      } catch {
        /* silent */
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

  const recent = jobs.slice(0, 8);
  const scheduled = jobs
    .filter((j) => j.status === "queued" || !!j.awaiting)
    .slice(0, 4);

  return (
    <div className="flex h-full overflow-hidden">
      {/* Main column */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-auto p-8 flex flex-col gap-10">
          {/* Make cards */}
          <section>
            <h2 className="text-[12px] font-semibold tracking-[0.08em] uppercase text-[var(--color-text-tertiary)] mb-4">
              What do you want to make?
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {MAKE_CARDS.map((card) => (
                <button
                  key={card.id}
                  type="button"
                  onClick={() => router.push(card.href)}
                  className="group relative overflow-hidden rounded-[12px] border p-6 text-left flex flex-col gap-3 transition-all duration-150"
                  style={{
                    background: "var(--color-surf-2)",
                    borderColor: "var(--color-hairline)",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = `${card.color}44`;
                    e.currentTarget.style.background = card.bg;
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "var(--color-hairline)";
                    e.currentTarget.style.background = "var(--color-surf-2)";
                  }}
                >
                  <div
                    className="relative h-24 rounded-lg overflow-hidden flex items-center justify-center"
                    style={{
                      background: `linear-gradient(135deg, ${card.bg}, var(--color-surf-1))`,
                      border: `1px solid ${card.color}22`,
                    }}
                  >
                    <div
                      className="stripes-soft absolute inset-0 pointer-events-none"
                      style={{ opacity: 0.08 }}
                      aria-hidden
                    />
                    <card.icon
                      size={32}
                      style={{ color: card.color, opacity: 0.7 }}
                    />
                  </div>
                  <div>
                    <div className="text-[15px] font-semibold text-[var(--color-text-primary)] tracking-[-0.02em] mb-1">
                      {card.label}
                    </div>
                    <div className="text-[12px] text-[var(--color-text-tertiary)]">
                      {card.sub}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </section>

          {/* Recent renders */}
          <section>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[12px] font-semibold tracking-[0.08em] uppercase text-[var(--color-text-tertiary)]">
                Recent Renders
              </h2>
              <Link
                href="/library"
                className="text-[12px] flex items-center gap-1 text-[var(--color-amber)]"
              >
                View all <ChevronRight size={12} />
              </Link>
            </div>
            {recent.length === 0 ? (
              <div className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-surf-1)] py-12 text-center text-[12px] text-[var(--color-text-tertiary)]">
                No renders yet — start with a Short above.
              </div>
            ) : (
              <div className="flex gap-4 overflow-x-auto pb-2">
                {recent.map((job) => (
                  <VideoTile
                    key={job.job_id}
                    data={jobToTile(job)}
                    size="md"
                    onClick={() => router.push(`/tasks?job=${job.job_id}`)}
                  />
                ))}
              </div>
            )}
          </section>
        </div>
      </div>

      {/* Right column */}
      <aside
        className="w-[280px] shrink-0 flex flex-col"
        style={{
          background: "var(--color-surf-1)",
          borderLeft: "1px solid var(--color-hairline)",
        }}
      >
        {/* Schedule / awaiting */}
        <div className="p-5 border-b border-[var(--color-hairline)]">
          <div className="flex items-center justify-between mb-[14px]">
            <span className="text-[12px] font-semibold tracking-[0.06em] uppercase text-[var(--color-text-tertiary)]">
              Active Jobs
            </span>
            <Calendar size={14} className="text-[var(--color-text-tertiary)]" />
          </div>
          {scheduled.length === 0 ? (
            <div className="text-[11px] text-[var(--color-text-tertiary)] py-2">
              Nothing in the queue.
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {scheduled.map((job) => (
                <Link
                  key={job.job_id}
                  href={`/tasks?job=${job.job_id}`}
                  className="flex items-center gap-[10px] px-[10px] py-2 rounded-md"
                  style={{
                    background: "var(--color-surf-2)",
                    border: "1px solid var(--color-hairline)",
                  }}
                >
                  <span
                    className="font-mono text-[11px] text-[var(--color-amber)] shrink-0 w-[42px] truncate"
                  >
                    {job.created_at ? relTime(job.created_at) : "—"}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[12px] font-medium text-[var(--color-text-primary)] truncate">
                      {job.topic || job.job_id.slice(0, 8)}
                    </div>
                    <div className="text-[10px] text-[var(--color-text-tertiary)]">
                      {job.account_id ? `${job.account_id.slice(0, 6)} · ` : ""}
                      {job.type}
                    </div>
                  </div>
                  <StatusPill
                    status={job.awaiting ? "pending" : "queued"}
                    size="xs"
                  />
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Disk usage */}
        <DiskWidget />

        {/* Quick stats */}
        <div className="p-5">
          <div className="grid grid-cols-2 gap-[10px]">
            {[
              { label: "Total Uploads", val: stats.total, color: "var(--color-text-primary)" },
              { label: "This Week", val: stats.week, color: "var(--color-success)" },
              { label: "Rendering", val: stats.rendering, color: "var(--color-warning)" },
              { label: "Failed", val: stats.failed, color: "var(--color-error)" },
            ].map((s) => (
              <div
                key={s.label}
                className="rounded-md p-3"
                style={{
                  background: "var(--color-surf-2)",
                  border: "1px solid var(--color-hairline)",
                }}
              >
                <div
                  className="text-[20px] font-bold tracking-[-0.02em] tabular-nums"
                  style={{ color: s.color }}
                >
                  {s.val}
                </div>
                <div className="text-[10px] text-[var(--color-text-tertiary)] mt-[2px]">
                  {s.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}

function DiskWidget() {
  // Static placeholder for now — backend has no /api/disk endpoint yet.
  const used = 2.3;
  const total = 10;
  const pct = Math.min(100, Math.round((used / total) * 100));
  return (
    <div className="p-5 border-b border-[var(--color-hairline)]">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[12px] font-semibold tracking-[0.06em] uppercase text-[var(--color-text-tertiary)]">
          Scratch Storage
        </span>
        <Database size={14} className="text-[var(--color-text-tertiary)]" />
      </div>
      <div className="font-mono text-[11px] text-[var(--color-text-secondary)] mb-2">
        .mp/ scratch · {used.toFixed(1)} GB
      </div>
      <div className="h-1 rounded-full bg-[var(--color-surf-3)] overflow-hidden mb-2">
        <div
          className="h-full rounded-full"
          style={{ width: `${pct}%`, background: "var(--color-amber)" }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-[var(--color-text-tertiary)]">
        <span>{used.toFixed(1)} GB used</span>
        <span>{total} GB total</span>
      </div>
      <button
        type="button"
        className="mt-3 w-full px-3 py-[7px] rounded-md text-[12px] flex items-center justify-center gap-[6px] transition-all duration-150"
        style={{
          background: "transparent",
          border: "1px solid var(--color-hairline)",
          color: "var(--color-text-secondary)",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = "rgba(248,113,113,0.27)";
          e.currentTarget.style.color = "var(--color-error)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = "var(--color-hairline)";
          e.currentTarget.style.color = "var(--color-text-secondary)";
        }}
      >
        <Trash2 size={12} />
        Clean scratch files
      </button>
    </div>
  );
}
