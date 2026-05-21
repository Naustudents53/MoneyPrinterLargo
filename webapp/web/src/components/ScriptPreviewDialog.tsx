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
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  CheckCircle2,
  Loader2,
  XCircle,
  RotateCw,
  Sparkles,
  PenLine,
  Volume2,
} from "lucide-react";
import { toast } from "sonner";
import { api, type RetentionMode } from "@/lib/api";

type Phase = "idle" | "running" | "ready" | "saving" | "error";

interface ScriptPreviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  channelId?: string;
  kind?: "short" | "long";
  retentionMode?: RetentionMode;
  /** SSE URL for /api/channels/{id}/preview-script. Null while closed. */
  sseUrl: string | null;
  /** Called when user approves the preview. Receives the preview id so the
   * caller can pass it to /generate?script_file=<id>. Also returns the subject
   * (which may have been edited) — useful for nicer dialog titles downstream. */
  onApprove: (data: { previewId: string; subject: string; script: string }) => void;
  /** Called when the user wants to regenerate with the same parameters. */
  onRegenerate: () => void;
}

/**
 * Two-stage flow:
 *   1. Stream the preview-script job logs.
 *   2. Once we see `PREVIEW_ID=<x>`, fetch the actual subject + script from
 *      the API and switch the dialog into an editable form so the user can
 *      tweak before approving the full render.
 */
export function ScriptPreviewDialog({
  open,
  onOpenChange,
  channelId = "",
  kind = "short",
  retentionMode = "standard",
  sseUrl,
  onApprove,
  onRegenerate,
}: ScriptPreviewDialogProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [logs, setLogs] = useState<string[]>([]);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [subject, setSubject] = useState("");
  const [script, setScript] = useState("");
  const [originalSubject, setOriginalSubject] = useState("");
  const [originalScript, setOriginalScript] = useState("");
  const [voiceLoading, setVoiceLoading] = useState(false);
  const [voiceUrl, setVoiceUrl] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const logBoxRef = useRef<HTMLDivElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const previewIdRef = useRef<string | null>(null);
  const jobIdRef = useRef<string | null>(null);
  const logsRef = useRef<string[]>([]);
  const reconnectAttemptsRef = useRef(0);
  const doneRef = useRef(false);

  useEffect(() => {
    return () => {
      if (voiceUrl) URL.revokeObjectURL(voiceUrl);
    };
  }, [voiceUrl]);

  // Connect to SSE when the dialog opens with a fresh sseUrl.
  useEffect(() => {
    if (!open || !sseUrl) return;
    setLogs([]);
    logsRef.current = [];
    setPreviewId(null);
    previewIdRef.current = null;
    doneRef.current = false;
    setSubject("");
    setScript("");
    setVoiceUrl(null);
    setVoiceLoading(false);
    setJobId(null);
    setCancelling(false);
    jobIdRef.current = null;
    reconnectAttemptsRef.current = 0;
    setPhase("running");

    const append = (line: string) => {
      setLogs((prev) => {
        const next = prev.length > 1500 ? [...prev.slice(-1000), line] : [...prev, line];
        logsRef.current = next;
        return next;
      });
    };

    const loadPreview = async (id: string) => {
      const data = await api.readPreview(id);
      setSubject(data.subject);
      setScript(data.script);
      setOriginalSubject(data.subject);
      setOriginalScript(data.script);
      setPhase("ready");
    };

    const resolvePreviewId = () => {
      if (previewIdRef.current) return previewIdRef.current;
      const joined = logsRef.current.join(" ");
      const m = /PREVIEW_ID=([A-Za-z0-9]+)/.exec(joined);
      return m?.[1] || "";
    };

    let reconnectTimer: number | undefined;

    const connect = (url: string, replay = false) => {
      const stream = new EventSource(url);
      esRef.current = stream;

      stream.addEventListener("start", (ev) => {
        try {
          const data = JSON.parse((ev as MessageEvent).data);
          if (data.job_id) {
            jobIdRef.current = data.job_id;
            setJobId(data.job_id);
          }
        } catch {
          // Older streams may not include JSON metadata.
        }
        append(replay ? "──── stream reconectado ────" : "──── preview iniciado ────");
      });

      stream.addEventListener("log", (ev) => {
        try {
          const data = JSON.parse((ev as MessageEvent).data);
          const line: string = data.line ?? "";
          const m = /PREVIEW_ID=([A-Za-z0-9]+)/.exec(line);
          if (m) {
            previewIdRef.current = m[1];
            setPreviewId(m[1]);
          }
          append(line);
        } catch {
          append((ev as MessageEvent).data);
        }
      });

      stream.addEventListener("done", async () => {
      doneRef.current = true;
      append("──── completado ✅ ────");
      stream.close();
      let id = resolvePreviewId();
      if (!id) {
        toast.error("No se obtuvo el id del preview");
        setPhase("error");
        return;
      }
      try {
        await loadPreview(id);
      } catch (e) {
        toast.error("No se pudo leer el preview: " + (e as Error).message);
        setPhase("error");
      }
      });

      stream.addEventListener("error", async (ev) => {
        if (doneRef.current) return;

        const maybeMessage = ev as MessageEvent;
        if (typeof maybeMessage.data === "string" && maybeMessage.data) {
          try {
            const payload = JSON.parse(maybeMessage.data);
            append(`──── proceso terminó con error (rc ${payload.rc ?? "?"}) ❌ ────`);
          } catch {
            append("──── proceso terminó con error ❌ ────");
          }
          stream.close();
          const id = resolvePreviewId();
          if (id) {
            try {
              await loadPreview(id);
              toast.warning("El proceso terminó con error, pero el preview quedó disponible.");
              return;
            } catch {
              // Fall through to the visible error state.
            }
          }
          setPhase("error");
          toast.error("Falló la generación del preview");
          return;
        }

        stream.close();
        const id = jobIdRef.current;
        if (id && reconnectAttemptsRef.current < 4) {
          reconnectAttemptsRef.current += 1;
          append(`──── stream interrumpido; reconectando (${reconnectAttemptsRef.current}/4) ────`);
          reconnectTimer = window.setTimeout(() => {
            connect(api.jobStreamUrl(id), true);
          }, 900);
          return;
        }

        append("──── error de conexión ❌ ────");
        setPhase("error");
        toast.error("Se perdió la conexión con el preview");
      });
    };

    connect(sseUrl);

    return () => {
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      esRef.current?.close();
      esRef.current = null;
    };
    // We intentionally exclude `previewId` and `logs` from deps so the SSE
    // connection isn't recreated when those state values update during the
    // stream — only the URL/open flips should reset it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, sseUrl]);

  useEffect(() => {
    if (logBoxRef.current) logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
  }, [logs]);

  // Reset when closing so a re-open starts clean.
  useEffect(() => {
    if (!open) {
      esRef.current?.close();
      esRef.current = null;
      setPhase("idle");
      setLogs([]);
      logsRef.current = [];
      setPreviewId(null);
      previewIdRef.current = null;
      setJobId(null);
      jobIdRef.current = null;
      reconnectAttemptsRef.current = 0;
      setCancelling(false);
      doneRef.current = false;
      setSubject("");
      setScript("");
      setVoiceUrl(null);
      setVoiceLoading(false);
    }
  }, [open]);

  const cancelPreview = async () => {
    const id = jobIdRef.current || jobId;
    setCancelling(true);
    try {
      if (id) {
        await api.stopJob(id);
        toast.message("Preview cancelado");
      }
      esRef.current?.close();
      esRef.current = null;
      setPhase("idle");
      onOpenChange(false);
    } catch (e) {
      toast.error("No se pudo cancelar: " + (e as Error).message);
      setCancelling(false);
    }
  };

  const approve = async () => {
    if (!previewId) {
      toast.error("Preview no listo todavía");
      return;
    }
    setPhase("saving");
    try {
      // If the user edited anything, persist back to disk so /generate picks
      // up the edits. Otherwise skip the round-trip — the file is already
      // exactly what the runner wrote.
      const edited =
        subject.trim() !== originalSubject.trim() ||
        script.trim() !== originalScript.trim();
      if (edited) {
        await api.savePreview(previewId, { subject: subject.trim(), script: script.trim() });
      }
      onApprove({ previewId, subject: subject.trim(), script: script.trim() });
      onOpenChange(false);
    } catch (e) {
      toast.error("No se pudo guardar: " + (e as Error).message);
      setPhase("ready");
    }
  };

  const listenVoice = async () => {
    if (!previewId) {
      toast.error("Preview no listo todavia");
      return;
    }
    if (!channelId) {
      toast.error("Selecciona un canal");
      return;
    }
    const trimmedSubject = subject.trim();
    const trimmedScript = script.trim();
    if (!trimmedSubject || !trimmedScript) {
      toast.error("El tema y el script son obligatorios");
      return;
    }

    setVoiceLoading(true);
    try {
      const edited =
        trimmedSubject !== originalSubject.trim() ||
        trimmedScript !== originalScript.trim();
      if (edited) {
        await api.savePreview(previewId, { subject: trimmedSubject, script: trimmedScript });
        setOriginalSubject(trimmedSubject);
        setOriginalScript(trimmedScript);
      }

      const res = await fetch(
        api.scriptVoicePreviewUrl(previewId, {
          channel_id: channelId,
          kind,
          retention_mode: retentionMode,
        }),
      );
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const body = await res.json();
          detail = body.detail || JSON.stringify(body);
        } catch {
          // ignore
        }
        throw new Error(`${res.status}: ${detail}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setVoiceUrl(url);
      window.setTimeout(() => {
        audioRef.current?.play().catch(() => undefined);
      }, 50);
    } catch (e) {
      toast.error("No se pudo generar la voz: " + (e as Error).message);
    } finally {
      setVoiceLoading(false);
    }
  };

  const sentenceCount = script
    .split(/[.!?]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0).length;

  return (
    <Dialog open={open} onOpenChange={(o) => (phase === "running" || phase === "saving" || cancelling ? null : onOpenChange(o))}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-1">
              <DialogTitle className="flex items-center gap-2">
                <PhaseIcon phase={phase} />
                Vista previa del script
              </DialogTitle>
              <DialogDescription>
                {phase === "running"
                  ? "Generando subject y script (sin imágenes ni render todavía)…"
                  : phase === "ready"
                  ? "Revisa y edita si quieres. Al continuar se hará el render completo."
                  : phase === "error"
                  ? "Algo falló — revisa los logs y reintenta."
                  : "Cargando…"}
              </DialogDescription>
            </div>
            {phase === "ready" && (
              <Badge variant="outline" className="font-mono">
                {sentenceCount} frases · {script.length} chars
              </Badge>
            )}
          </div>
        </DialogHeader>

        {phase === "ready" || phase === "saving" ? (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="preview-subject">Tema</Label>
              <Input
                id="preview-subject"
                value={subject}
                onChange={(e) => {
                  setSubject(e.target.value);
                  setVoiceUrl(null);
                }}
                disabled={phase === "saving"}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="preview-script">Script</Label>
              <Textarea
                id="preview-script"
                rows={14}
                value={script}
                onChange={(e) => {
                  setScript(e.target.value);
                  setVoiceUrl(null);
                }}
                disabled={phase === "saving"}
                className="font-mono text-[13px] leading-relaxed"
              />
              <p className="text-xs text-muted-foreground">
                Edita libremente. Si cambias la cantidad de frases, el video
                resultará más corto/largo de lo que pediste.
              </p>
            </div>
            {voiceUrl && (
              <audio
                ref={audioRef}
                src={voiceUrl}
                controls
                className="h-9 w-full"
              />
            )}
          </div>
        ) : (
          <div
            ref={logBoxRef}
            className="font-mono text-[12px] leading-relaxed bg-[#0b1220] text-emerald-200 rounded-lg border border-border/60 p-4 h-[280px] overflow-auto scrollbar-thin"
          >
            {logs.length === 0 ? (
              <div className="text-emerald-200/40 italic flex items-center gap-2">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Esperando salida…
              </div>
            ) : (
              logs.map((l, i) => (
                <div key={i} className="whitespace-pre-wrap break-words">
                  <span className={lineClass(l)}>{l}</span>
                </div>
              ))
            )}
          </div>
        )}

        <DialogFooter className="gap-2 flex-wrap">
          {phase === "ready" && (
            <>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={listenVoice}
                disabled={voiceLoading || !channelId}
              >
                {voiceLoading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Volume2 className="h-3.5 w-3.5" />
                )}
                Escuchar voz
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="gap-2"
                onClick={() => onRegenerate()}
              >
                <RotateCw className="h-3.5 w-3.5" /> Regenerar
              </Button>
              <Button
                variant="brand"
                size="sm"
                className="gap-2"
                onClick={approve}
              >
                <Sparkles className="h-3.5 w-3.5" /> Aprobar y continuar render
              </Button>
            </>
          )}
          {phase === "saving" && (
            <Button disabled size="sm" className="gap-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Guardando…
            </Button>
          )}
          {phase === "running" && (
            <Button
              variant="destructive"
              size="sm"
              className="gap-2"
              disabled={cancelling}
              onClick={cancelPreview}
            >
              {cancelling ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <XCircle className="h-3.5 w-3.5" />
              )}
              {cancelling ? "Cancelando" : "Cancelar"}
            </Button>
          )}
          {(phase === "error" || phase === "idle") && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onOpenChange(false)}
            >
              Cerrar
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PhaseIcon({ phase }: { phase: Phase }) {
  if (phase === "running" || phase === "saving")
    return <Loader2 className="h-5 w-5 animate-spin text-primary" />;
  if (phase === "ready") return <PenLine className="h-5 w-5 text-emerald-400" />;
  if (phase === "error") return <XCircle className="h-5 w-5 text-destructive" />;
  return <CheckCircle2 className="h-5 w-5 text-muted-foreground" />;
}

function lineClass(line: string) {
  const l = line.toLowerCase();
  if (l.includes("error") || l.includes("❌")) return "text-rose-300";
  if (l.includes("warning") || l.includes("⚠")) return "text-amber-300";
  if (l.includes("success") || l.includes("✅") || l.includes("done") || l.includes("preview_id")) return "text-emerald-300";
  if (l.startsWith("[runner]")) return "text-sky-300";
  if (l.startsWith("ℹ")) return "text-violet-300";
  return "text-emerald-200";
}
