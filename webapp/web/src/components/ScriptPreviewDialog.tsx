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
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

type Phase = "idle" | "running" | "ready" | "saving" | "error";

interface ScriptPreviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
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
  const esRef = useRef<EventSource | null>(null);
  const logBoxRef = useRef<HTMLDivElement | null>(null);

  // Connect to SSE when the dialog opens with a fresh sseUrl.
  useEffect(() => {
    if (!open || !sseUrl) return;
    setLogs([]);
    setPreviewId(null);
    setSubject("");
    setScript("");
    setPhase("running");

    const es = new EventSource(sseUrl);
    esRef.current = es;

    const append = (line: string) =>
      setLogs((prev) => (prev.length > 1500 ? [...prev.slice(-1000), line] : [...prev, line]));

    es.addEventListener("start", () => {
      append("──── preview iniciado ────");
    });
    es.addEventListener("log", (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent).data);
        const line: string = data.line ?? "";
        // Capture the id printed by run_job.py:cmd_preview_script.
        const m = /PREVIEW_ID=([A-Za-z0-9]+)/.exec(line);
        if (m) setPreviewId(m[1]);
        append(line);
      } catch {
        append((ev as MessageEvent).data);
      }
    });
    es.addEventListener("done", async () => {
      append("──── completado ✅ ────");
      es.close();
      // Re-read the latest previewId from state via closure — but state may
      // not have flushed yet in the same tick. Pull it from the logs as a
      // fallback so we never miss it.
      const idFromState = previewId;
      let id = idFromState;
      if (!id) {
        const joined = logs.concat([" "]).join(" ");
        const m = /PREVIEW_ID=([A-Za-z0-9]+)/.exec(joined);
        if (m) id = m[1];
      }
      if (!id) {
        toast.error("No se obtuvo el id del preview");
        setPhase("error");
        return;
      }
      try {
        const data = await api.readPreview(id);
        setSubject(data.subject);
        setScript(data.script);
        setOriginalSubject(data.subject);
        setOriginalScript(data.script);
        setPhase("ready");
      } catch (e) {
        toast.error("No se pudo leer el preview: " + (e as Error).message);
        setPhase("error");
      }
    });
    es.addEventListener("error", () => {
      append("──── error ❌ ────");
      setPhase("error");
      es.close();
      toast.error("Falló la generación del preview");
    });

    return () => {
      es.close();
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
      setPreviewId(null);
      setSubject("");
      setScript("");
    }
  }, [open]);

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

  const sentenceCount = script
    .split(/[.!?]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0).length;

  return (
    <Dialog open={open} onOpenChange={(o) => (phase === "running" || phase === "saving" ? null : onOpenChange(o))}>
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
                onChange={(e) => setSubject(e.target.value)}
                disabled={phase === "saving"}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="preview-script">Script</Label>
              <Textarea
                id="preview-script"
                rows={14}
                value={script}
                onChange={(e) => setScript(e.target.value)}
                disabled={phase === "saving"}
                className="font-mono text-[13px] leading-relaxed"
              />
              <p className="text-xs text-muted-foreground">
                Edita libremente. Si cambias la cantidad de frases, el video
                resultará más corto/largo de lo que pediste.
              </p>
            </div>
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
          {(phase === "running" || phase === "error" || phase === "idle") && (
            <Button
              variant="outline"
              size="sm"
              disabled={phase === "running"}
              onClick={() => onOpenChange(false)}
            >
              {phase === "running" ? "Espera…" : "Cerrar"}
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
