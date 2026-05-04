"use client";

import { motion } from "framer-motion";
import { Film, Monitor, Smartphone, Download, Video, Sparkles, Check, AlertTriangle } from "lucide-react";
import { useProjectStore } from "@/stores/project";
import { RenderProgress } from "@/components/studio/RenderProgress";
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import {
  getAccounts,
  createJob,
  cancelJob,
  API_BASE,
  type JobEvent,
  type AccountItem,
} from "@/lib/api";
import { useJobEvents } from "@/lib/useJobEvents";

const PLATFORMS = [
  { id: "youtube", label: "YouTube", icon: <Video size={20} />, aspect: "16:9", res: "1920 × 1080" },
  { id: "youtube-shorts", label: "YouTube Shorts", icon: <Smartphone size={20} />, aspect: "9:16", res: "1080 × 1920" },
  { id: "tiktok", label: "TikTok", icon: <Monitor size={20} />, aspect: "9:16", res: "1080 × 1920" },
];

export function StageExport({ onComplete }: { onComplete?: () => void }) {
  const { projects, currentProjectId, updateExportSettings } = useProjectStore();
  const project = projects.find((p) => p.id === currentProjectId);
  const exportSettings = project?.exportSettings ?? { resolution: "1080p" as const, format: "mp4" as const, platform: "youtube" as const };

  const [rendering, setRendering] = useState(false);
  const [progress, setProgress] = useState(0);
  const [done, setDone] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [videoPath, setVideoPath] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [cancelled, setCancelled] = useState(false);

  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>("");
  const [loadingAccounts, setLoadingAccounts] = useState(true);

  const logsEndRef = useRef<HTMLDivElement>(null);
  const onCompleteRef = useRef(onComplete);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    let mounted = true;
    getAccounts()
      .then((acc) => {
        if (!mounted) return;
        setAccounts(acc);
        if (acc.length > 0 && !selectedAccountId) {
          setSelectedAccountId(acc[0].id);
        }
      })
      .catch(() => {
        // ignore
      })
      .finally(() => {
        if (mounted) setLoadingAccounts(false);
      });
    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [logs]);

  const handlers = useMemo(
    () => ({
      "stage.progress": (e: Extract<JobEvent, { type: "stage.progress" }>) => {
        setProgress(Math.round(e.percent));
      },
      log: (e: Extract<JobEvent, { type: "log" }>) => {
        setLogs((prev) => [
          ...prev,
          `[${new Date().toLocaleTimeString()}] ${e.level.toUpperCase()}: ${e.message}`,
        ]);
      },
      done: (e: Extract<JobEvent, { type: "done" }>) => {
        setDone(true);
        setRendering(false);
        setVideoPath(e.artifacts?.video || "");
        onCompleteRef.current?.();
      },
      error: (e: Extract<JobEvent, { type: "error" }>) => {
        setError(e.message);
        setRendering(false);
      },
      cancelled: () => {
        setCancelled(true);
        setRendering(false);
      },
    }),
    []
  );

  useJobEvents(jobId, handlers);

  const startRender = useCallback(async () => {
    if (!selectedAccountId) return;
    setRendering(true);
    setProgress(0);
    setDone(false);
    setError(null);
    setCancelled(false);
    setLogs([]);
    setVideoPath("");
    try {
      const res = await createJob({
        type: "recap",
        topic: project?.movieTitle || "",
        account_id: selectedAccountId,
      });
      setJobId(res.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start job");
      setRendering(false);
    }
  }, [selectedAccountId, project]);

  const handleCancel = useCallback(async () => {
    if (!jobId) return;
    try {
      await cancelJob(jobId);
    } catch {
      // ignore
    }
  }, [jobId]);

  const videoSrc = useMemo(() => {
    if (!done) return "";
    if (videoPath) {
      return videoPath.startsWith("http")
        ? videoPath
        : `${API_BASE}${videoPath.startsWith("/") ? "" : "/"}${videoPath}`;
    }
    if (jobId) {
      return `${API_BASE}/api/jobs/${jobId}/artifact/video`;
    }
    return "";
  }, [done, videoPath, jobId]);

  return (
    <motion.div className="h-full flex" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}>
      <div className="flex-1 flex flex-col items-center justify-center p-8 gap-6">
        <motion.div
          className="relative w-full max-w-xl aspect-video rounded-2xl overflow-hidden"
          style={{
            border: "1px solid rgba(30,30,50,0.5)",
            background: "linear-gradient(135deg, #08080F, #06060A)",
            boxShadow: "inset 0 1px 0 rgba(255,255,255,0.02), 0 16px 48px rgba(0,0,0,0.5)",
          }}
          whileHover={{ scale: 1.01 }}
        >
          {done && videoSrc ? (
            <video
              src={videoSrc}
              controls
              className="w-full h-full object-contain"
              style={{ background: "#000" }}
            />
          ) : (
            <>
              <div
                className="absolute inset-0"
                style={{
                  background: "linear-gradient(135deg, rgba(232,162,79,0.06), transparent, rgba(96,165,250,0.04))",
                }}
              />
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="text-center">
                  <Film size={48} className="mx-auto mb-2" style={{ color: "rgba(232,162,79,0.25)" }} />
                  <span className="text-sm text-text-muted">{project?.movieTitle || "Metropolis — AI Recap"}</span>
                </div>
              </div>
              {done && !videoSrc && (
                <motion.div
                  className="absolute inset-0 flex items-center justify-center"
                  style={{ background: "rgba(0,0,0,0.5)" }}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                >
                  <div
                    className="w-16 h-16 rounded-full flex items-center justify-center"
                    style={{
                      background: "rgba(16,185,129,0.1)",
                      border: "1px solid rgba(16,185,129,0.3)",
                    }}
                  >
                    <Check size={28} style={{ color: "#10B981" }} />
                  </div>
                </motion.div>
              )}
            </>
          )}
        </motion.div>

        <div className="flex items-center gap-3">
          {PLATFORMS.map((p) => (
            <motion.button
              key={p.id}
              className="flex flex-col items-center gap-1.5 px-5 py-3 rounded-xl border transition-all"
              style={
                exportSettings.platform === p.id
                  ? {
                      background: "rgba(232,162,79,0.06)",
                      border: "1px solid rgba(232,162,79,0.2)",
                      color: "#F4C58A",
                    }
                  : {
                      background: "rgba(255,255,255,0.02)",
                      border: "1px solid rgba(30,30,50,0.5)",
                      color: "#5A5A7A",
                    }
              }
              whileHover={{
                y: -2,
                borderColor: exportSettings.platform === p.id ? "rgba(232,162,79,0.35)" : "rgba(30,30,50,0.8)",
              }}
              whileTap={{ scale: 0.97 }}
              onClick={() => updateExportSettings({ platform: p.id as typeof exportSettings.platform })}
            >
              {p.icon}
              <span className="text-[10px] font-medium">{p.label}</span>
              <span className="text-[9px] text-text-muted">{p.aspect} · {p.res}</span>
            </motion.button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted mr-2">Res</span>
          {(["1080p", "720p", "480p"] as const).map((r) => (
            <motion.button
              key={r}
              className="px-3 py-1.5 rounded-lg text-xs font-mono transition-all"
              style={
                exportSettings.resolution === r
                  ? {
                      background: "rgba(232,162,79,0.08)",
                      color: "#F4C58A",
                      border: "1px solid rgba(232,162,79,0.2)",
                    }
                  : {
                      background: "rgba(255,255,255,0.02)",
                      border: "1px solid rgba(30,30,50,0.5)",
                      color: "#5A5A7A",
                    }
              }
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => updateExportSettings({ resolution: r })}
            >
              {r}
            </motion.button>
          ))}
        </div>
      </div>

      <div
        className={cn(
          "w-[340px] flex flex-col p-6 gap-4",
          rendering || done ? "justify-start" : "items-center justify-center"
        )}
        style={{
          borderLeft: "1px solid rgba(30,30,50,0.5)",
          background: "linear-gradient(180deg, rgba(6,6,16,0.5), rgba(8,8,15,0.3))",
        }}
      >
        {rendering || done ? (
          <>
            <RenderProgress
              progress={Math.min(Math.round(progress), 100)}
              eta={done ? "Done" : error ? "Error" : cancelled ? "Cancelled" : `~${Math.ceil((100 - progress) / 15)}s`}
              fileSizeEstimate={exportSettings.resolution === "1080p" ? "850 MB" : "480 MB"}
              currentOperation={
                done
                  ? "Export complete"
                  : error
                  ? "Export failed"
                  : cancelled
                  ? "Export cancelled"
                  : progress < 40
                  ? "Encoding video..."
                  : progress < 70
                  ? "Mixing audio..."
                  : "Writing file..."
              }
            />

            {error && (
              <div
                className="flex items-center gap-2 rounded-lg border px-3 py-2 text-xs"
                style={{ borderColor: "rgba(239,68,68,0.2)", background: "rgba(239,68,68,0.06)", color: "#F87171" }}
              >
                <AlertTriangle size={14} /> {error}
              </div>
            )}
            {cancelled && (
              <div
                className="flex items-center gap-2 rounded-lg border px-3 py-2 text-xs"
                style={{ borderColor: "rgba(245,158,11,0.2)", background: "rgba(245,158,11,0.06)", color: "#FBBF24" }}
              >
                <AlertTriangle size={14} /> Cancelled
              </div>
            )}

            <div className="flex-1 min-h-0 flex flex-col rounded-xl border overflow-hidden" style={{ borderColor: "rgba(30,30,50,0.5)", background: "rgba(6,6,16,0.4)" }}>
              <div
                className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted"
                style={{ borderBottom: "1px solid rgba(30,30,50,0.5)" }}
              >
                Live Log
              </div>
              <div className="flex-1 overflow-y-auto p-3 space-y-1 font-mono text-[10px]">
                {logs.map((log, i) => (
                  <div key={i} className="truncate" style={{ color: "#5A5A7A" }}>
                    {log}
                  </div>
                ))}
                <div ref={logsEndRef} />
              </div>
            </div>

            {!done && !error && !cancelled && (
              <button
                onClick={handleCancel}
                className="w-full py-2 rounded-xl text-xs font-medium transition-all"
                style={{
                  background: "rgba(255,255,255,0.02)",
                  border: "1px solid rgba(30,30,50,0.5)",
                  color: "#9090B0",
                }}
              >
                Cancel Render
              </button>
            )}
          </>
        ) : (
          <div className="text-center w-full">
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4"
              style={{
                background: "rgba(232,162,79,0.06)",
                border: "1px solid rgba(232,162,79,0.15)",
              }}
            >
              <Sparkles size={28} style={{ color: "rgba(167,139,250,0.6)" }} />
            </div>

            <div className="mb-4 text-left">
              <label className="block text-[10px] font-semibold uppercase tracking-wider text-text-muted mb-2">
                Account
              </label>
              {loadingAccounts ? (
                <div className="text-xs text-text-muted">Loading accounts…</div>
              ) : (
                <select
                  className="w-full px-3 py-2 rounded-xl text-xs text-text-primary outline-none"
                  style={{
                    background: "rgba(255,255,255,0.03)",
                    border: "1px solid rgba(30,30,50,0.5)",
                  }}
                  value={selectedAccountId}
                  onChange={(e) => setSelectedAccountId(e.target.value)}
                >
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.nickname || a.handle} ({a.platform})
                    </option>
                  ))}
                </select>
              )}
            </div>

            <h3 className="text-base font-semibold text-text-primary mb-1">Ready to Export</h3>
            <p className="text-xs text-text-muted mb-6">
              {project?.movieTitle || "Metropolis Recap"} · ~15 min · {exportSettings.resolution} MP4
            </p>
            <motion.button
              className="flex items-center justify-center gap-2 w-full py-3 rounded-xl text-white text-sm font-medium transition-all mb-3"
              style={{
                background: "linear-gradient(135deg, #E8A24F, #C47A28)",
                boxShadow: "0 0 20px rgba(232,162,79,0.2), inset 0 1px 0 rgba(255,255,255,0.1)",
                border: "1px solid rgba(232,162,79,0.3)",
              }}
              whileHover={{
                scale: 1.02,
                boxShadow: "0 0 30px rgba(232,162,79,0.3), inset 0 1px 0 rgba(255,255,255,0.15)",
              }}
              whileTap={{ scale: 0.98 }}
              disabled={!selectedAccountId || loadingAccounts}
              onClick={startRender}
            >
              <Download size={16} />Export Video
            </motion.button>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    disabled
                    className="flex items-center justify-center gap-2 w-full py-3 rounded-xl text-sm transition-all cursor-not-allowed"
                    style={{
                      background: "rgba(255,255,255,0.02)",
                      border: "1px solid rgba(30,30,50,0.5)",
                      color: "#9090B0",
                    }}
                  >
                    <Video size={16} />Export & Upload
                  </button>
                </TooltipTrigger>
                <TooltipContent>Upload after rendering completes</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        )}
      </div>
    </motion.div>
  );
}
