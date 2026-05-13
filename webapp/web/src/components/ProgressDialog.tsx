import { useEffect, useMemo, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  CheckCircle2,
  Loader2,
  XCircle,
  X,
  Copy,
  Eye,
  UploadCloud,
  Square,
  Download,
  ArrowDown,
  Terminal,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

type Status = "idle" | "running" | "done" | "error";

interface ProgressDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  /** SSE endpoint URL. When the dialog opens, an EventSource connects here. */
  sseUrl: string | null;
  /** If provided, post-generation actions (revisar / subir) are shown for this channel. */
  channelId?: string;
  /** Kind of content being generated — required so upload-last picks the right YouTube flow. */
  kind?: "short" | "long";
  /** When true, auto-opens the preview modal as soon as the render finishes. */
  previewOnFinish?: boolean;
  /** When true (and previewOnFinish), starts the upload-last job once the user closes the preview. */
  uploadAfterPreview?: boolean;
  onDone?: () => void;
}

const SEPARATOR_RE = /^─{2,}\s*(.+?)\s*─{2,}$/;

/**
 * Streaming progress dialog. Connects to the SSE endpoint and shows logs in
 * a terminal-style panel with elapsed time and status. Same vibe as watching
 * the CLI run, but in the browser.
 *
 * After a generation job completes, parses `[runner] Generated: <path>` from
 * the logs and offers to preview the video or trigger an upload-last job.
 */
export function ProgressDialog({
  open,
  onOpenChange,
  title,
  description,
  sseUrl,
  channelId,
  kind = "short",
  previewOnFinish = false,
  uploadAfterPreview = false,
  onDone,
}: ProgressDialogProps) {
  const [logs, setLogs] = useState<string[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const [generatedFile, setGeneratedFile] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [activeUrl, setActiveUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<"generate" | "upload">("generate");
  const [stickToBottom, setStickToBottom] = useState(true);
  const esRef = useRef<EventSource | null>(null);
  const logBoxRef = useRef<HTMLDivElement | null>(null);
  // Hold onDone in a ref so changes to its identity (parent re-renders with a
  // non-memoized callback) don't retrigger the SSE effect and spawn a duplicate
  // job on the backend.
  const onDoneRef = useRef(onDone);
  useEffect(() => {
    onDoneRef.current = onDone;
  }, [onDone]);
  // Auto-open the preview modal exactly once per render-completion. Resets
  // whenever a new job starts. A separate flag tracks whether closing the
  // preview should chain into upload-last.
  const previewAutoOpenedRef = useRef(false);
  const uploadOnPreviewCloseRef = useRef(false);

  // (Re)connect when sseUrl changes (initial open OR upload-last triggered).
  useEffect(() => {
    if (!open || !activeUrl) return;
    setLogs([]);
    setElapsed(0);
    setStatus("running");
    setJobId(null);
    setStickToBottom(true);
    if (phase === "generate") {
      setGeneratedFile(null);
      previewAutoOpenedRef.current = false;
      uploadOnPreviewCloseRef.current = false;
    }

    const es = new EventSource(activeUrl);
    esRef.current = es;

    const append = (line: string) =>
      setLogs((prev) => (prev.length > 5000 ? [...prev.slice(-4500), line] : [...prev, line]));

    es.addEventListener("start", (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent).data);
        if (data.job_id) setJobId(data.job_id);
      } catch {
        /* ignore */
      }
      append("──── job iniciado ────");
    });
    es.addEventListener("log", (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent).data);
        if (typeof data.elapsed === "number") setElapsed(data.elapsed);
        const line: string = data.line ?? "";
        const m = /\[runner\]\s+Generated:\s+(.+)$/.exec(line);
        if (m) {
          const full = m[1].trim();
          const name = full.replace(/^.*[\\/]/, "");
          setGeneratedFile(name);
        }
        append(line);
      } catch {
        append((ev as MessageEvent).data);
      }
    });
    es.addEventListener("done", (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent).data);
        setElapsed(data.elapsed || 0);
      } catch {
        /* ignore */
      }
      append("──── completado ✅ ────");
      setStatus("done");
      es.close();
      onDoneRef.current?.();
      toast.success(phase === "upload" ? "Video subido" : "Render completado");
    });
    es.addEventListener("error", (ev) => {
      try {
        const msg = (ev as MessageEvent).data
          ? JSON.parse((ev as MessageEvent).data)
          : null;
        if (msg) append(`──── error (rc=${msg.rc}) ❌ ────`);
      } catch {
        append("──── conexión perdida ────");
      }
      setStatus("error");
      es.close();
      toast.error("El proceso terminó con error");
    });

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [open, activeUrl, phase]);

  // Initial sseUrl → activeUrl mirror when the dialog opens.
  useEffect(() => {
    if (open && sseUrl) {
      setPhase("generate");
      setActiveUrl(sseUrl);
    }
    if (!open) {
      setActiveUrl(null);
      setGeneratedFile(null);
      setJobId(null);
      previewAutoOpenedRef.current = false;
      uploadOnPreviewCloseRef.current = false;
    }
  }, [open, sseUrl]);

  // When the render finishes and the user asked for a preview at the end,
  // auto-open the preview modal once. Remember whether closing it should
  // chain into upload-last so we can fire it from onOpenChange.
  useEffect(() => {
    if (
      previewOnFinish &&
      status === "done" &&
      phase === "generate" &&
      generatedFile &&
      !previewAutoOpenedRef.current
    ) {
      previewAutoOpenedRef.current = true;
      uploadOnPreviewCloseRef.current = uploadAfterPreview && !!channelId;
      setPreviewOpen(true);
    }
  }, [previewOnFinish, status, phase, generatedFile, uploadAfterPreview, channelId]);

  // Smart auto-scroll: only pin to bottom while the user hasn't scrolled away.
  useEffect(() => {
    if (stickToBottom && logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
    }
  }, [logs, stickToBottom]);

  // Reset stick state when the box is repopulated (new job).
  useEffect(() => {
    if (logs.length === 0) setStickToBottom(true);
  }, [logs.length]);

  const handleLogScroll = () => {
    const el = logBoxRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setStickToBottom(distanceFromBottom < 32);
  };

  const jumpToBottom = () => {
    const el = logBoxRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    setStickToBottom(true);
  };

  const stopAndClose = async () => {
    if (jobId) {
      try {
        await api.stopJob(jobId);
        toast.message("Proceso detenido");
      } catch (e) {
        toast.error("No se pudo detener: " + (e as Error).message);
      }
    }
    esRef.current?.close();
    setStatus("idle");
    onOpenChange(false);
  };

  const closeWithoutStopping = () => {
    esRef.current?.close();
    onOpenChange(false);
  };

  const copyLogs = async () => {
    try {
      await navigator.clipboard.writeText(logs.join("\n"));
      toast.success("Logs copiados");
    } catch {
      toast.error("No se pudieron copiar los logs");
    }
  };

  const downloadLogs = () => {
    try {
      const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
      const blob = new Blob([logs.join("\n")], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `mpl-logs-${stamp}.txt`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("No se pudieron descargar los logs");
    }
  };

  const triggerUpload = () => {
    if (!channelId) return;
    setPhase("upload");
    setActiveUrl(api.uploadLastUrl(channelId, kind));
  };

  const handlePreviewOpenChange = (next: boolean) => {
    setPreviewOpen(next);
    if (!next && uploadOnPreviewCloseRef.current) {
      uploadOnPreviewCloseRef.current = false;
      triggerUpload();
    }
  };

  const canPreview = !!generatedFile && status === "done" && phase === "generate";
  // Show the upload button when generation finished AND when an upload itself
  // failed — the second case lets the user retry without leaving the dialog.
  const canUpload =
    !!channelId &&
    ((status === "done" && phase === "generate") || (status === "error" && phase === "upload"));

  // Find a "--- summary ---" block at the tail of the log to highlight visually.
  const summaryRange = useMemo(() => findSummaryRange(logs), [logs]);

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => (status === "running" ? null : onOpenChange(o))}>
        <DialogContent className="max-w-3xl gap-5">
          <DialogHeader className="space-y-3">
            <div className="flex items-start justify-between gap-6">
              <div className="space-y-1.5 min-w-0 flex-1">
                <DialogTitle className="flex items-center gap-2.5 text-base">
                  <StatusIcon status={status} />
                  <span className="truncate">
                    {phase === "upload" ? "Subiendo a YouTube" : title}
                  </span>
                </DialogTitle>
                {description && (
                  <DialogDescription className="text-[13px] leading-relaxed">
                    {description}
                  </DialogDescription>
                )}
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <StatusBadge status={status} />
                <Badge
                  variant="outline"
                  className="font-mono text-[11px] tabular-nums px-2 py-0.5"
                  title="Tiempo transcurrido"
                >
                  {formatElapsed(elapsed)}
                </Badge>
              </div>
            </div>
          </DialogHeader>

          <div className="relative">
            <div className="flex items-center justify-between px-3 py-1.5 rounded-t-lg border border-b-0 hairline-strong bg-[hsl(var(--ink)/0.95)] text-emerald-200/70">
              <div className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-wider">
                <Terminal className="h-3 w-3" />
                <span>logs</span>
                {logs.length > 0 && (
                  <span className="text-emerald-200/40 normal-case tracking-normal">
                    · {logs.length} líneas
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1.5">
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    status === "running"
                      ? "bg-primary animate-pulse"
                      : status === "done"
                      ? "bg-success"
                      : status === "error"
                      ? "bg-destructive"
                      : "bg-emerald-200/30"
                  }`}
                />
                <span className="text-[10px] font-mono uppercase tracking-widest">
                  {status === "running" ? "live" : status === "done" ? "ready" : status === "error" ? "failed" : "idle"}
                </span>
              </div>
            </div>

            <div
              ref={logBoxRef}
              onScroll={handleLogScroll}
              className="font-mono text-[12px] leading-relaxed bg-[hsl(var(--ink))] text-emerald-200 rounded-b-lg border hairline-strong p-4 h-[420px] overflow-auto scrollbar-thin"
            >
              {logs.length === 0 ? (
                <div className="text-emerald-200/40 italic flex items-center gap-2">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Esperando salida…
                </div>
              ) : (
                logs.map((l, i) => {
                  const sep = SEPARATOR_RE.exec(l);
                  if (sep) {
                    return <LogDivider key={i} label={sep[1]} />;
                  }
                  const inSummary =
                    summaryRange &&
                    i >= summaryRange.start &&
                    i <= summaryRange.end;
                  return (
                    <div
                      key={i}
                      className={`group flex gap-2 px-1 -mx-1 rounded transition-colors hover:bg-emerald-300/[0.04] ${
                        inSummary ? "bg-emerald-300/[0.05]" : ""
                      }`}
                    >
                      <span className="text-emerald-200/25 select-none tabular-nums w-10 text-right shrink-0">
                        {String(i + 1).padStart(3, " ")}
                      </span>
                      <span className={`whitespace-pre-wrap break-words flex-1 ${lineClass(l)}`}>
                        {l || " "}
                      </span>
                    </div>
                  );
                })
              )}
            </div>

            {!stickToBottom && logs.length > 0 && (
              <Button
                size="sm"
                variant="brand"
                onClick={jumpToBottom}
                className="absolute bottom-3 right-4 gap-1.5 h-7 px-2.5 text-[11px] shadow-lg shadow-black/40"
              >
                <ArrowDown className="h-3 w-3" />
                Saltar al final
              </Button>
            )}
          </div>

          <DialogFooter className="gap-2 flex-wrap sm:justify-between">
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={copyLogs}
                disabled={logs.length === 0}
                className="gap-1.5 h-8 px-2.5 text-xs"
              >
                <Copy className="h-3.5 w-3.5" /> Copiar
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={downloadLogs}
                disabled={logs.length === 0}
                className="gap-1.5 h-8 px-2.5 text-xs"
              >
                <Download className="h-3.5 w-3.5" /> Descargar
              </Button>
            </div>

            <div className="flex items-center gap-2 flex-wrap justify-end">
              {canPreview && (
                <Button variant="outline" size="sm" onClick={() => setPreviewOpen(true)} className="gap-1.5">
                  <Eye className="h-3.5 w-3.5" /> Revisar video
                </Button>
              )}
              {canUpload && (
                <Button variant="brand" size="sm" onClick={triggerUpload} className="gap-1.5">
                  <UploadCloud className="h-3.5 w-3.5" />
                  {status === "error" && phase === "upload" ? "Reintentar subida" : "Subir a YouTube"}
                </Button>
              )}

              {status === "running" ? (
                <>
                  <Button variant="ghost" size="sm" onClick={closeWithoutStopping} className="gap-1.5">
                    <X className="h-3.5 w-3.5" /> Cerrar (sigue en background)
                  </Button>
                  <Button variant="destructive" size="sm" onClick={stopAndClose} className="gap-1.5">
                    <Square className="h-3.5 w-3.5" /> Detener
                  </Button>
                </>
              ) : (
                <Button variant="default" size="sm" onClick={() => onOpenChange(false)}>
                  Cerrar
                </Button>
              )}
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={previewOpen} onOpenChange={handlePreviewOpenChange}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Vista previa: {generatedFile}</DialogTitle>
            <DialogDescription>
              {uploadOnPreviewCloseRef.current
                ? "Al cerrar, se inicia la subida a YouTube."
                : "Revisa el render antes de subirlo a YouTube."}
            </DialogDescription>
          </DialogHeader>
          {generatedFile && (
            <video
              controls
              autoPlay
              className="w-full rounded-md bg-black max-h-[70vh]"
              src={api.mp4RawUrl(generatedFile)}
            />
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => handlePreviewOpenChange(false)}>
              {uploadOnPreviewCloseRef.current ? "Cerrar y subir" : "Cerrar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function StatusIcon({ status }: { status: Status }) {
  if (status === "running") return <Loader2 className="h-4 w-4 animate-spin text-primary shrink-0" />;
  if (status === "done") return <CheckCircle2 className="h-4 w-4 text-success shrink-0" />;
  if (status === "error") return <XCircle className="h-4 w-4 text-destructive shrink-0" />;
  return null;
}

function StatusBadge({ status }: { status: Status }) {
  if (status === "running") {
    return (
      <Badge variant="default" className="gap-1.5 px-2 py-0.5 text-[11px] font-medium">
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inset-0 rounded-full bg-primary-foreground/70 animate-ping" />
          <span className="relative h-1.5 w-1.5 rounded-full bg-primary-foreground" />
        </span>
        Ejecutando
      </Badge>
    );
  }
  if (status === "done") {
    return (
      <Badge variant="success" className="px-2 py-0.5 text-[11px] font-medium">
        Completado
      </Badge>
    );
  }
  if (status === "error") {
    return (
      <Badge variant="destructive" className="px-2 py-0.5 text-[11px] font-medium">
        Error
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="px-2 py-0.5 text-[11px] font-medium">
      Listo
    </Badge>
  );
}

function LogDivider({ label }: { label: string }) {
  const tone = /error|conexión|❌/i.test(label)
    ? "text-rose-300 border-rose-300/30"
    : /completado|✅/i.test(label)
    ? "text-emerald-300 border-emerald-300/30"
    : "text-sky-300 border-sky-300/30";
  return (
    <div className="flex items-center gap-3 my-2 select-none">
      <div className={`flex-1 border-t ${tone}`} />
      <span className={`text-[10px] font-mono uppercase tracking-[0.18em] ${tone.split(" ")[0]}`}>
        {label}
      </span>
      <div className={`flex-1 border-t ${tone}`} />
    </div>
  );
}

function formatElapsed(s: number) {
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const r = Math.floor(s - m * 60);
  return `${m}m ${r}s`;
}

function lineClass(line: string) {
  const l = line.toLowerCase();
  if (l.includes("error") || l.includes("traceback") || l.includes("❌")) return "text-rose-300";
  if (l.includes("warning") || l.includes("⚠")) return "text-amber-300";
  if (l.includes("success") || l.includes("✅") || l.includes("uploaded")) return "text-emerald-300";
  if (/^\s*wrote:/i.test(line)) return "text-emerald-300";
  if (/^\s*\+\s/.test(line)) return "text-lima";
  if (/→\s*reclassif|→\s*pruned|→\s*added/.test(line)) return "text-violeta";
  if (/^\s*meta\s+\d+\/\d+/.test(line)) return "text-sky-300/90";
  if (l.startsWith("[runner]")) return "text-sky-300";
  if (l.startsWith("ℹ")) return "text-violet-300";
  return "text-emerald-200";
}

/**
 * Locate a "--- summary ---" block in the tail of the log so we can render
 * it with a soft highlight. Returns the inclusive line range or null.
 */
function findSummaryRange(logs: string[]): { start: number; end: number } | null {
  for (let i = logs.length - 1; i >= 0; i--) {
    if (/^---\s*summary\s*---/i.test(logs[i].trim())) {
      let end = logs.length - 1;
      // Stop at the next separator-style marker after the summary header.
      for (let j = i + 1; j < logs.length; j++) {
        if (SEPARATOR_RE.test(logs[j].trim())) {
          end = j - 1;
          break;
        }
      }
      return { start: i, end };
    }
  }
  return null;
}
