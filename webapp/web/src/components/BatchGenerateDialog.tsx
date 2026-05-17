import { useEffect, useMemo, useState } from "react";
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
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Layers,
  Loader2,
  Plus,
  Trash2,
  UploadCloud,
  AlertTriangle,
} from "lucide-react";
import { toast } from "sonner";
import {
  api,
  type Channel,
  type BatchJobItem,
  type BatchJobResult,
  type RetentionMode,
  type ShortRenderProfile,
} from "@/lib/api";
import { cn } from "@/lib/utils";

interface BatchRow {
  rowId: string; // local-only id for React keys; not sent
  channelId: string;
  count: number;       // how many shorts to generate for this channel
  customTopic: string; // optional — same topic across all N for this channel
}

interface BatchGenerateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  channels: Channel[];
  /** Defaults to inherit from the main Generate page so the batch feels like
   * a multiplier of the single-job config (model, duration, hook style…). */
  defaults: {
    kind: "short" | "long";
    imageMode: "ai" | "photos";
    autoUpload: boolean;
    model?: string;
    sentenceLength?: number;
    hookStyle?: string;
    renderProfile?: ShortRenderProfile;
    retentionMode?: RetentionMode;
  };
}

/**
 * Multi-channel parallel-launcher. The user adds rows (one per channel) and
 * sets a count + optional topic. We expand the rows into a flat job list and
 * POST it to /api/generate-batch, which spawns one subprocess per job.
 *
 * Note: the dialog deliberately does NOT stream individual job logs — that
 * would mean opening N EventSources at once and is the wrong UX for a launcher.
 * Instead it shows the spawned job ids and tells the user to watch the global
 * "Background jobs" panel.
 */
export function BatchGenerateDialog({
  open,
  onOpenChange,
  channels,
  defaults,
}: BatchGenerateDialogProps) {
  const [rows, setRows] = useState<BatchRow[]>([]);
  const [autoUpload, setAutoUpload] = useState(defaults.autoUpload);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{
    jobs: BatchJobResult[];
    spawned: number;
  } | null>(null);

  // When the dialog opens fresh, seed with one empty row (or one row per
  // channel if there are only 2-3 channels, so the user sees the multi-row
  // pattern immediately).
  useEffect(() => {
    if (!open) return;
    setResult(null);
    setAutoUpload(defaults.autoUpload);
    if (rows.length === 0 && channels.length > 0) {
      setRows([
        {
          rowId: cryptoRandomId(),
          channelId: channels[0].id,
          count: 1,
          customTopic: "",
        },
      ]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const totalJobs = useMemo(
    () => rows.reduce((acc, r) => acc + Math.max(0, r.count || 0), 0),
    [rows],
  );

  const addRow = () => {
    if (channels.length === 0) return;
    // Pick a channel not already used in another row (cycling). If all are
    // used, just reuse the first one — duplicate rows are allowed (the user
    // may want 2 batches with different topics for the same channel).
    const used = new Set(rows.map((r) => r.channelId));
    const fresh = channels.find((c) => !used.has(c.id)) || channels[0];
    setRows((prev) => [
      ...prev,
      {
        rowId: cryptoRandomId(),
        channelId: fresh.id,
        count: 1,
        customTopic: "",
      },
    ]);
  };

  const removeRow = (rowId: string) => {
    setRows((prev) => prev.filter((r) => r.rowId !== rowId));
  };

  const updateRow = (rowId: string, patch: Partial<BatchRow>) => {
    setRows((prev) =>
      prev.map((r) => (r.rowId === rowId ? { ...r, ...patch } : r)),
    );
  };

  const submit = async () => {
    if (totalJobs === 0) {
      toast.error("Agrega al menos un canal");
      return;
    }
    if (totalJobs > 25) {
      toast.error("Máximo 25 jobs por lote (límite de seguridad)");
      return;
    }

    // Expand rows → flat jobs. Each row contributes `count` identical jobs;
    // the runner will fan out topics automatically because each job runs in
    // its own subprocess and (when customTopic is empty) calls generate_topic
    // with the duplicate-guard active.
    const jobs: BatchJobItem[] = [];
    for (const r of rows) {
      const n = Math.max(1, Math.min(10, r.count | 0));
      for (let i = 0; i < n; i++) {
        jobs.push({
          channel_id: r.channelId,
          kind: defaults.kind,
          custom_topic: r.customTopic.trim() || undefined,
          image_mode: defaults.imageMode,
          auto_upload: autoUpload,
          model: defaults.model || undefined,
          sentence_length: defaults.sentenceLength,
          hook_style: defaults.hookStyle || undefined,
          render_profile: defaults.renderProfile,
          retention_mode: defaults.retentionMode,
        });
      }
    }

    setSubmitting(true);
    try {
      const out = await api.generateBatch(jobs);
      setResult(out);
      toast.success(`${out.spawned} jobs en marcha`);
    } catch (e) {
      toast.error("Falló el lanzamiento: " + (e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => (submitting ? null : onOpenChange(o))}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Layers className="h-5 w-5 text-primary" /> Generación en lote
          </DialogTitle>
          <DialogDescription>
            Lanza varios shorts en paralelo. Cada canal corre en su propio
            proceso aislado — distintos perfiles de Firefox, distintos archivos.
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <BatchResultSummary result={result} onClose={() => onOpenChange(false)} />
        ) : (
          <div className="space-y-4">
            {/* Inherits the main page config so users see what's about to apply */}
            <InheritedConfigBar defaults={defaults} totalJobs={totalJobs} />

            <div className="space-y-2">
              <Label>Canales en este lote</Label>
              <div className="space-y-2">
                {rows.length === 0 && (
                  <div className="text-sm text-muted-foreground italic">
                    Sin filas — agrega al menos un canal.
                  </div>
                )}
                {rows.map((r, i) => (
                  <div
                    key={r.rowId}
                    className="flex flex-col sm:flex-row gap-2 items-stretch sm:items-center border border-border/60 rounded-lg p-2 bg-muted/20"
                  >
                    <div className="flex items-center gap-2 sm:w-48 shrink-0">
                      <Badge variant="outline" className="font-mono text-[10px]">
                        #{i + 1}
                      </Badge>
                      <Select
                        value={r.channelId}
                        onValueChange={(v) => updateRow(r.rowId, { channelId: v })}
                      >
                        <SelectTrigger className="h-8 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {channels.map((c) => (
                            <SelectItem key={c.id} value={c.id}>
                              {c.nickname}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <Input
                      placeholder="Tema personalizado (opcional, se aplica a las N copias)"
                      value={r.customTopic}
                      onChange={(e) => updateRow(r.rowId, { customTopic: e.target.value })}
                      className="h-8 text-xs flex-1"
                    />
                    <div className="flex items-center gap-2">
                      <Label className="text-xs text-muted-foreground">N</Label>
                      <Input
                        type="number"
                        min={1}
                        max={10}
                        value={r.count}
                        onChange={(e) =>
                          updateRow(r.rowId, { count: parseInt(e.target.value || "1", 10) })
                        }
                        className="h-8 text-xs w-16 text-center tabular-nums"
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        onClick={() => removeRow(r.rowId)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={addRow}
                disabled={channels.length === 0}
                className="gap-2"
              >
                <Plus className="h-3.5 w-3.5" /> Agregar canal
              </Button>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-border p-3">
              <div className="space-y-0.5">
                <Label className="flex items-center gap-1.5">
                  <UploadCloud className="h-4 w-4" /> Subir automáticamente
                </Label>
                <p className="text-xs text-muted-foreground">
                  Al terminar cada render, abre una ventana de Firefox por canal
                  para subir. Funciona porque ya separamos perfiles.
                </p>
              </div>
              <Switch checked={autoUpload} onCheckedChange={setAutoUpload} />
            </div>

            {totalJobs > 10 && (
              <div className="flex items-start gap-2 rounded-lg border border-amber-300/40 bg-amber-300/5 p-3 text-xs text-amber-300">
                <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                <span>
                  <b>{totalJobs} jobs en paralelo</b> es mucho. Con free tier de
                  Gemini vas a chocar el RPM (5/min). Considera usar Gemma 4 31B
                  o Ollama, o reduce el lote.
                </span>
              </div>
            )}
          </div>
        )}

        {!result && (
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button
              variant="brand"
              onClick={submit}
              disabled={submitting || totalJobs === 0}
              className="gap-2"
            >
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Layers className="h-4 w-4" />
              )}
              {submitting ? "Lanzando…" : `Lanzar ${totalJobs} job${totalJobs === 1 ? "" : "s"}`}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}

function InheritedConfigBar({
  defaults,
  totalJobs,
}: {
  defaults: BatchGenerateDialogProps["defaults"];
  totalJobs: number;
}) {
  return (
    <div className="rounded-lg border border-border/60 bg-muted/30 p-3 text-xs space-y-1.5">
      <div className="font-semibold text-foreground">Config heredada del panel principal:</div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
        <span>Tipo: <span className="text-foreground font-medium">{defaults.kind}</span></span>
        <span>Imágenes: <span className="text-foreground font-medium">{defaults.imageMode}</span></span>
        {defaults.model && (
          <span>Modelo: <span className="text-foreground font-medium">{defaults.model}</span></span>
        )}
        {defaults.sentenceLength ? (
          <span>Frases: <span className="text-foreground font-medium">{defaults.sentenceLength}</span></span>
        ) : null}
        {defaults.hookStyle && (
          <span>Hook: <span className="text-foreground font-medium">{defaults.hookStyle.split("::")[1] || defaults.hookStyle}</span></span>
        )}
        {defaults.renderProfile && (
          <span>Render: <span className="text-foreground font-medium">{defaults.renderProfile}</span></span>
        )}
        {defaults.retentionMode && defaults.retentionMode !== "standard" && (
          <span>Modo: <span className="text-foreground font-medium">MAXIMA RETENCION</span></span>
        )}
        <span>Total jobs: <span className="text-foreground font-medium tabular-nums">{totalJobs}</span></span>
      </div>
    </div>
  );
}

function BatchResultSummary({
  result,
  onClose,
}: {
  result: { jobs: BatchJobResult[]; spawned: number };
  onClose: () => void;
}) {
  const failed = result.jobs.filter((j) => !j.ok);
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 text-sm">
        <div className="font-semibold text-emerald-300 flex items-center gap-2">
          ✅ {result.spawned} jobs en ejecución
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          Mira el progreso en el panel de "Background jobs" (esquina superior).
          Cada job es independiente — si uno falla los demás siguen.
        </p>
      </div>
      <div className="space-y-1.5 max-h-[40vh] overflow-auto scrollbar-thin">
        {result.jobs.map((j, i) => (
          <div
            key={i}
            className={cn(
              "flex items-center justify-between gap-2 rounded-md border p-2 text-xs",
              j.ok ? "border-border/60 bg-muted/20" : "border-rose-500/30 bg-rose-500/5",
            )}
          >
            <div className="flex items-center gap-2 min-w-0">
              <Badge variant={j.ok ? "outline" : "destructive"} className="text-[10px]">
                {j.ok ? "ok" : "error"}
              </Badge>
              <span className="font-medium truncate">
                {j.channel_nickname || j.channel_id}
              </span>
              {j.kind && (
                <span className="text-muted-foreground">· {j.kind}</span>
              )}
            </div>
            {j.ok ? (
              <span className="font-mono text-[10px] text-muted-foreground">
                {j.job_id}
              </span>
            ) : (
              <span className="text-rose-300 text-[10px]">{j.error}</span>
            )}
          </div>
        ))}
      </div>
      {failed.length > 0 && (
        <div className="text-xs text-rose-300">
          {failed.length} fallaron antes de lanzarse. Los demás corren normal.
        </div>
      )}
      <DialogFooter>
        <Button onClick={onClose}>Cerrar</Button>
      </DialogFooter>
    </div>
  );
}

function cryptoRandomId(): string {
  // 8-char URL-safe id. Cryptographic strength isn't needed — these only key
  // React rows; we just want low collision probability across many adds.
  const bytes = new Uint8Array(6);
  crypto.getRandomValues(bytes);
  return Array.from(bytes)
    .map((b) => b.toString(36).padStart(2, "0"))
    .join("")
    .slice(0, 8);
}
