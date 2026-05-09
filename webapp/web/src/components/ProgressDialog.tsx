import { useEffect, useRef, useState } from "react";
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
  onDone?: () => void;
}

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
  const esRef = useRef<EventSource | null>(null);
  const logBoxRef = useRef<HTMLDivElement | null>(null);
  // Hold onDone in a ref so changes to its identity (parent re-renders with a
  // non-memoized callback) don't retrigger the SSE effect and spawn a duplicate
  // job on the backend.
  const onDoneRef = useRef(onDone);
  useEffect(() => {
    onDoneRef.current = onDone;
  }, [onDone]);

  // (Re)connect when sseUrl changes (initial open OR upload-last triggered).
  useEffect(() => {
    if (!open || !activeUrl) return;
    setLogs([]);
    setElapsed(0);
    setStatus("running");
    setJobId(null);
    if (phase === "generate") setGeneratedFile(null);

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
    }
  }, [open, sseUrl]);

  // Auto-scroll logs
  useEffect(() => {
    if (logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
    }
  }, [logs]);

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

  const triggerUpload = () => {
    if (!channelId) return;
    setPhase("upload");
    setActiveUrl(api.uploadLastUrl(channelId, kind));
  };

  const canPreview = !!generatedFile && status === "done" && phase === "generate";
  // Show the upload button when generation finished AND when an upload itself
  // failed — the second case lets the user retry without leaving the dialog.
  const canUpload =
    !!channelId &&
    ((status === "done" && phase === "generate") || (status === "error" && phase === "upload"));

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => (status === "running" ? null : onOpenChange(o))}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <div className="flex items-center justify-between gap-4">
              <div className="space-y-1">
                <DialogTitle className="flex items-center gap-2">
                  <StatusIcon status={status} />
                  {phase === "upload" ? "Subiendo a YouTube" : title}
                </DialogTitle>
                {description && <DialogDescription>{description}</DialogDescription>}
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={statusVariant(status)}>
                  {status === "running" && "Ejecutando…"}
                  {status === "done" && "Completado"}
                  {status === "error" && "Error"}
                  {status === "idle" && "Listo"}
                </Badge>
                <Badge variant="outline" className="font-mono">
                  {formatElapsed(elapsed)}
                </Badge>
              </div>
            </div>
          </DialogHeader>

          <div
            ref={logBoxRef}
            className="font-mono text-[12px] leading-relaxed bg-[#0b1220] text-emerald-200 rounded-lg border border-border/60 p-4 h-[420px] overflow-auto scrollbar-thin"
          >
            {logs.length === 0 ? (
              <div className="text-emerald-200/40 italic flex items-center gap-2">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Esperando salida…
              </div>
            ) : (
              logs.map((l, i) => (
                <div key={i} className="whitespace-pre-wrap break-words">
                  <span className="text-emerald-200/30 mr-2 select-none">
                    {String(i + 1).padStart(4, " ")}
                  </span>
                  <span className={lineClass(l)}>{l}</span>
                </div>
              ))
            )}
          </div>

          <DialogFooter className="gap-2 flex-wrap">
            <Button variant="ghost" size="sm" onClick={copyLogs} className="gap-2">
              <Copy className="h-3.5 w-3.5" /> Copiar logs
            </Button>

            {canPreview && (
              <Button variant="outline" size="sm" onClick={() => setPreviewOpen(true)} className="gap-2">
                <Eye className="h-3.5 w-3.5" /> Revisar video
              </Button>
            )}
            {canUpload && (
              <Button variant="brand" size="sm" onClick={triggerUpload} className="gap-2">
                <UploadCloud className="h-3.5 w-3.5" />
                {status === "error" && phase === "upload" ? "Reintentar subida" : "Subir a YouTube"}
              </Button>
            )}

            {status === "running" ? (
              <>
                <Button variant="destructive" size="sm" onClick={stopAndClose} className="gap-2">
                  <Square className="h-3.5 w-3.5" /> Detener proceso
                </Button>
                <Button variant="ghost" size="sm" onClick={closeWithoutStopping} className="gap-2">
                  <X className="h-3.5 w-3.5" /> Cerrar (sigue en background)
                </Button>
              </>
            ) : (
              <Button variant="default" size="sm" onClick={() => onOpenChange(false)}>
                Cerrar
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Vista previa: {generatedFile}</DialogTitle>
            <DialogDescription>
              Revisa el render antes de subirlo a YouTube.
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
            <Button variant="outline" onClick={() => setPreviewOpen(false)}>
              Cerrar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function StatusIcon({ status }: { status: Status }) {
  if (status === "running") return <Loader2 className="h-5 w-5 animate-spin text-primary" />;
  if (status === "done") return <CheckCircle2 className="h-5 w-5 text-success" />;
  if (status === "error") return <XCircle className="h-5 w-5 text-destructive" />;
  return null;
}

function statusVariant(s: Status) {
  if (s === "done") return "success" as const;
  if (s === "error") return "destructive" as const;
  if (s === "running") return "default" as const;
  return "outline" as const;
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
  if (l.includes("success") || l.includes("✅") || l.includes("done") || l.includes("uploaded")) return "text-emerald-300";
  if (l.startsWith("[runner]")) return "text-sky-300";
  if (l.startsWith("ℹ")) return "text-violet-300";
  return "text-emerald-200";
}
