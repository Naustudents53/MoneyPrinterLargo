"use client";

import { useEffect, useMemo, useState } from "react";
import { Search, X, RefreshCw, ExternalLink } from "lucide-react";
import { listJobs, type JobSummary } from "@/lib/api";
import { StatusPill, type PillStatus } from "@/components/ui/status-pill";
import { PlatformGlyph } from "@/components/ui/platform-glyph";

const STATUS_OPTIONS: { id: PillStatus | "all"; label: string }[] = [
  { id: "all",       label: "All" },
  { id: "uploaded",  label: "Uploaded" },
  { id: "rendering", label: "Rendering" },
  { id: "draft",     label: "Draft" },
  { id: "failed",    label: "Failed" },
];

interface LibraryRow {
  id: string;
  title: string;
  platform: string;
  duration: string;
  date: string;
  status: PillStatus;
  views: string | null;
  aspect: "9:16" | "16:9";
  thumb: string;
  account: string;
  videoUrl: string | null;
}

function jobToRow(job: JobSummary): LibraryRow {
  const status: PillStatus =
    job.status === "done" && job.has_video
      ? "uploaded"
      : job.status === "running" || job.status === "uploading"
      ? "rendering"
      : job.status === "error"
      ? "failed"
      : job.status === "cancelled"
      ? "draft"
      : "draft";
  const isLong = job.type === "long";
  return {
    id: job.job_id,
    title: job.topic || `Job ${job.job_id.slice(0, 8)}`,
    platform: "youtube",
    duration: isLong ? "~18:00" : "~0:45",
    date: job.created_at ? relTime(job.created_at) : "—",
    status,
    views: null,
    aspect: isLong ? "16:9" : "9:16",
    thumb: isLong ? "#1A3D2A" : "#3D2A1A",
    account: job.account_id || "—",
    videoUrl: job.video_url,
  };
}

function relTime(iso: string): string {
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

export function LibraryFrame() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [filterStatus, setFilterStatus] = useState<PillStatus | "all">("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

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

  const rows: LibraryRow[] = useMemo(() => jobs.map(jobToRow), [jobs]);

  const filtered = rows.filter((r) => {
    if (filterStatus !== "all" && r.status !== filterStatus) return false;
    if (search && !r.title.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const selectedRow = selected ? rows.find((r) => r.id === selected) ?? null : null;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Filters bar */}
      <div
        className="flex items-center gap-3 px-6 h-12 border-b border-[var(--color-hairline)] shrink-0"
      >
        {/* Search */}
        <div
          className="flex items-center gap-2 rounded-md px-[10px] h-8 w-[220px] shrink-0"
          style={{
            background: "var(--color-surf-2)",
            border: "1px solid var(--color-hairline)",
          }}
        >
          <Search size={13} className="text-[var(--color-text-tertiary)]" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search…"
            className="bg-transparent border-0 outline-none text-[12px] text-[var(--color-text-primary)] w-full"
          />
        </div>

        {/* Status pills */}
        <div className="flex gap-1">
          {STATUS_OPTIONS.map((opt) => {
            const active = filterStatus === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => setFilterStatus(opt.id)}
                className="px-[10px] py-1 rounded-md text-[11px] font-medium transition-colors duration-150"
                style={{
                  background: active ? "var(--color-amber-dim)" : "var(--color-surf-2)",
                  color: active ? "var(--color-amber)" : "var(--color-text-secondary)",
                  border: `1px solid ${
                    active ? "var(--color-amber-ring)" : "var(--color-hairline)"
                  }`,
                }}
              >
                {opt.label}
              </button>
            );
          })}
        </div>

        <div className="flex-1" />

        <span className="font-mono text-[11px] text-[var(--color-text-tertiary)]">
          {filtered.length} results
        </span>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* Table */}
        <div className="flex-1 overflow-auto">
          <table className="w-full text-[12px] border-collapse">
            <thead>
              <tr className="border-b border-[var(--color-hairline)]">
                {["", "Title", "Account", "Platform", "Duration", "Created", "Status", "Views"].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-2 text-left font-semibold text-[11px] uppercase tracking-[0.04em] text-[var(--color-text-tertiary)] whitespace-nowrap sticky top-0 z-10"
                      style={{ background: "var(--color-surf-1)" }}
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td
                    colSpan={8}
                    className="text-center text-[12px] text-[var(--color-text-tertiary)] py-12"
                  >
                    No jobs match this filter.
                  </td>
                </tr>
              )}
              {filtered.map((r) => {
                const isSel = r.id === selected;
                return (
                  <tr
                    key={r.id}
                    onClick={() => setSelected(isSel ? null : r.id)}
                    className="border-b cursor-pointer transition-colors duration-75"
                    style={{
                      borderColor: "var(--color-hairline-soft)",
                      background: isSel ? "var(--color-amber-dim)" : "transparent",
                    }}
                    onMouseEnter={(e) => {
                      if (!isSel) e.currentTarget.style.background = "var(--color-surf-2)";
                    }}
                    onMouseLeave={(e) => {
                      if (!isSel) e.currentTarget.style.background = "transparent";
                    }}
                  >
                    <td className="px-4 py-[10px]" style={{ width: 56 }}>
                      <div
                        className="flex items-center justify-center rounded border border-[var(--color-hairline)]"
                        style={{
                          width: r.aspect === "9:16" ? 28 : 48,
                          height: r.aspect === "9:16" ? 50 : 27,
                          background: `linear-gradient(135deg, ${r.thumb}, ${r.thumb}88)`,
                        }}
                      >
                        <span className="font-mono text-[7px] text-white/25">{r.aspect}</span>
                      </div>
                    </td>
                    <td className="px-4 py-[10px] max-w-[280px]">
                      <div className="text-[var(--color-text-primary)] font-medium truncate">
                        {r.title}
                      </div>
                    </td>
                    <td className="px-4 py-[10px] text-[var(--color-text-secondary)] truncate max-w-[140px]">
                      {r.account}
                    </td>
                    <td className="px-4 py-[10px]">
                      <PlatformGlyph platform={r.platform} />
                    </td>
                    <td className="px-4 py-[10px] font-mono text-[var(--color-text-secondary)]">
                      {r.duration}
                    </td>
                    <td className="px-4 py-[10px] text-[var(--color-text-tertiary)] whitespace-nowrap">
                      {r.date}
                    </td>
                    <td className="px-4 py-[10px]">
                      <StatusPill status={r.status} size="xs" />
                    </td>
                    <td
                      className="px-4 py-[10px] font-mono"
                      style={{
                        color: r.views ? "var(--color-success)" : "var(--color-text-tertiary)",
                      }}
                    >
                      {r.views || "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Drawer */}
        {selectedRow && (
          <aside
            className="w-[300px] shrink-0 flex flex-col overflow-auto"
            style={{
              background: "var(--color-surf-1)",
              borderLeft: "1px solid var(--color-hairline)",
            }}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-hairline)]">
              <span className="text-[12px] font-semibold text-[var(--color-text-primary)]">
                Details
              </span>
              <button
                type="button"
                onClick={() => setSelected(null)}
                className="p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]"
              >
                <X size={14} />
              </button>
            </div>
            <div className="p-5">
              <div
                className="w-full mb-4 rounded-md flex items-center justify-center border border-[var(--color-hairline)]"
                style={{
                  aspectRatio: selectedRow.aspect === "9:16" ? "9/16" : "16/9",
                  background: `linear-gradient(135deg, ${selectedRow.thumb}, ${selectedRow.thumb}88)`,
                }}
              >
                <span className="font-mono text-[11px] text-white/20">{selectedRow.aspect}</span>
              </div>
              <div className="text-[13px] font-semibold text-[var(--color-text-primary)] mb-2 leading-[1.4]">
                {selectedRow.title}
              </div>
              <StatusPill status={selectedRow.status} />

              <div className="mt-4 flex flex-col gap-2">
                {[
                  { label: "Duration", val: selectedRow.duration },
                  { label: "Created", val: selectedRow.date },
                  { label: "Account", val: selectedRow.account },
                  { label: "Views", val: selectedRow.views || "—" },
                ].map((m) => (
                  <div key={m.label} className="flex justify-between text-[12px]">
                    <span className="text-[var(--color-text-tertiary)]">{m.label}</span>
                    <span className="font-mono text-[var(--color-text-primary)] truncate ml-2">
                      {m.val}
                    </span>
                  </div>
                ))}
              </div>

              <div className="mt-5 flex flex-col gap-2">
                <button
                  type="button"
                  className="w-full px-2 py-2 rounded-md flex items-center justify-center gap-[6px] text-[12px] font-semibold"
                  style={{ background: "var(--color-amber)", color: "#0B0B0D" }}
                >
                  <RefreshCw size={12} />
                  Regenerate from here
                </button>
                {selectedRow.videoUrl && (
                  <a
                    href={selectedRow.videoUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="w-full px-2 py-2 rounded-md flex items-center justify-center gap-[6px] text-[12px]"
                    style={{
                      background: "transparent",
                      border: "1px solid var(--color-hairline)",
                      color: "var(--color-text-secondary)",
                    }}
                  >
                    <ExternalLink size={12} />
                    Open on YouTube
                  </a>
                )}
              </div>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
