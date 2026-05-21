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
import { api, type UploadPlatform } from "@/lib/api";

type Status = "idle" | "running" | "done" | "error";

type RenderProgress = {
  active: boolean;
  done: boolean;
  percent: number;
  frame: string;
  fps: string;
  time: string;
  durationLabel: string;
  speed: string;
  size: string;
  bitrate: string;
};

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
  /** Upload targets used by post-render upload buttons and preview chaining. */
  uploadPlatforms?: UploadPlatform[];
  onDone?: () => void;
}

const SEPARATOR_RE = /^─{2,}\s*(.+?)\s*─{2,}$/;
const ANSI_RE = /\x1b\[[0-9;]*m/g;

function normalizeLogLine(line: string) {
  return line
    .replace(ANSI_RE, "")
    .replace(/Â·/g, "-")
    .replace(/â†’/g, "->")
    .replace(/âœ“/g, "ok")
    .replace(/â€”|â€“/g, "-")
    .replace(/\s+$/g, "");
}

function compactPath(path: string) {
  return path.trim().replace(/^["']|["']$/g, "").replace(/^.*[\\/]/, "");
}

function providerLabel(provider: string) {
  const key = provider.trim().toLowerCase();
  const labels: Record<string, string> = {
    gemini: "Gemini",
    openai: "OpenAI",
    claude: "Claude",
    ollama: "Ollama",
    pollinations: "Pollinations",
  };
  return labels[key] ?? provider;
}

function yesNo(value: string) {
  return /^(true|yes|1)$/i.test(value) ? "si" : "no";
}

function describeTopic(topic: string) {
  const clean = topic.trim();
  if (!clean || /^\(auto/.test(clean)) return "tema automatico";
  return `tema: ${clean}`;
}

function formatInputType(type: string, fileName: string) {
  const ext = fileName.split(".").pop()?.toLowerCase();
  if (type === "image2") return "imagen";
  if (type === "wav") return "voz WAV";
  if (type === "mp3") return "musica MP3";
  if (ext === "mp4") return "video MP4";
  return type;
}

function cleanFfmpegPrefix(line: string) {
  return line.replace(/^\[[^\]]+\]\s*/, "").trim();
}

function clampPercent(value: number) {
  return Math.max(0, Math.min(100, value));
}

function parseClockSeconds(value: string) {
  const match = /^(\d+):(\d{2}):(\d{2}(?:\.\d+)?)$/.exec(value.trim());
  if (!match) return null;
  return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]);
}

function formatClock(seconds: number | null | undefined) {
  if (!seconds || seconds <= 0) return "--:--";
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${m}:${String(s).padStart(2, "0")}`;
}

function extractFfmpegFrameFields(line: string) {
  const fields: Record<string, string> = {};
  for (const match of line.matchAll(/\b(frame|fps|q|size|Lsize|time|bitrate|speed|elapsed)=\s*([^\s]+)/g)) {
    fields[match[1]] = match[2];
  }
  return fields.frame ? fields : null;
}

function parseFfmpegFrameProgress(line: string, durationSeconds: number | null): RenderProgress | null {
  const fields = extractFfmpegFrameFields(line);
  if (!fields) return null;
  const final = Boolean(fields.Lsize) || /\sLsize=/.test(line);
  const currentSeconds = fields.time ? parseClockSeconds(fields.time) : null;
  const percent = durationSeconds && currentSeconds !== null
    ? clampPercent((currentSeconds / durationSeconds) * 100)
    : final
    ? 100
    : 0;
  const size = fields.Lsize || fields.size || "?";
  return {
    active: true,
    done: final || percent >= 99.9,
    percent,
    frame: fields.frame,
    fps: fields.fps || "-",
    time: fields.time || "00:00:00.00",
    durationLabel: formatClock(durationSeconds),
    speed: fields.speed || "-",
    size,
    bitrate: fields.bitrate && fields.bitrate !== "N/A" ? fields.bitrate : "-",
  };
}

function ffmpegInputType(line: string) {
  return /^Input #\d+,\s*([^,]+),\s*from '/.exec(line)?.[1] ?? "";
}

function detectedDurationSeconds(line: string) {
  const match = /^\s*Duration:\s*([^,]+),/.exec(line);
  return match ? parseClockSeconds(match[1]) : null;
}

function isFfmpegDetailLine(line: string) {
  return (
    /^Input #\d+,\s*[^,]+,\s*from '/.test(line) ||
    /^Output #\d+,\s*[^,]+,\s*to '/.test(line) ||
    /^\s*Duration:\s*[^,]+,/.test(line) ||
    /^\s*Stream #\d+:\d+/.test(line) ||
    /^Stream mapping:/.test(line) ||
    /^\s*(?:Metadata|Side data):\s*$/.test(line) ||
    /^\s*(?:encoder|CPB properties)\s*:/.test(line) ||
    /^\[aist#/.test(line) ||
    /^\[out#/.test(line) ||
    /^\[aac /.test(line)
  );
}

function formatTechnicalProgressLine(line: string): string | null {
  let match = /^Input #(\d+),\s*([^,]+),\s*from '(.+)':$/.exec(line);
  if (match) {
    const fileName = compactPath(match[3]);
    return `Entrada ${match[1]}: ${formatInputType(match[2], fileName)} - ${fileName}`;
  }

  match = /^Output #(\d+),\s*([^,]+),\s*to '(.+)':$/.exec(line);
  if (match) return `Salida ${match[1]}: ${match[2].toUpperCase()} - ${compactPath(match[3])}`;

  match = /^\s*Duration:\s*([^,]+),\s*start:\s*([^,]+),\s*bitrate:\s*(.+)$/.exec(line);
  if (match) return `Duracion detectada: ${match[1]} | inicio ${match[2]} | bitrate ${match[3]}`;

  match = /^\s*Stream #(\d+):(\d+).*Video:\s*([^,]+).*?(\d+x\d+).*?(?:(\d+(?:\.\d+)?) fps)/.exec(line);
  if (match) {
    const codec = match[3].replace(/\s*\(.+?\)/g, "").trim();
    return `Video #${match[1]}:${match[2]}: ${match[4]}, ${match[5]} fps, codec ${codec}`;
  }

  match = /^\s*Stream #(\d+):(\d+).*Audio:\s*([^,]+).*?,\s*(\d+ Hz),\s*([^,]+)(?:,\s*([^,]+\/s))?/.exec(line);
  if (match) {
    const bitrate = match[6] ? `, ${match[6].trim()}` : "";
    return `Audio #${match[1]}:${match[2]}: ${match[3].trim()}, ${match[4]}, ${match[5].trim()}${bitrate}`;
  }

  if (/^Stream mapping:/.test(line)) return "Mapeo de streams:";

  match = /^\s*Stream #(\d+):(\d+).+?->\s*(.+)$/.exec(line);
  if (match) return `Mapa: entrada #${match[1]}:${match[2]} -> ${match[3]}`;

  match = /^\s*(.+?)\s+->\s+Stream #(\d+):(\d+)\s+\(([^)]+)\)$/.exec(line);
  if (match) return `Mapa: ${match[1]} -> salida #${match[2]}:${match[3]} (${match[4]})`;

  match = /^\s*Metadata:\s*$/.exec(line);
  if (match) return "Metadata:";

  match = /^\s*encoder\s*:\s*(.+)$/.exec(line);
  if (match) return `Encoder: ${match[1]}`;

  match = /^\s*Side data:\s*$/.exec(line);
  if (match) return "Datos extra del stream:";

  match = /^\s*CPB properties:\s*(.+)$/.exec(line);
  if (match) return `Buffer/bitrate video: ${match[1]}`;

  if (extractFfmpegFrameFields(line)) return null;

  if (/^\[Parsed_ass_/.test(line)) {
    const body = cleanFfmpegPrefix(line);
    match = /^Loading font file '(.+)'$/.exec(body);
    if (match) return `Fuente de subtitulos: ${compactPath(match[1])}`;
    match = /^Error opening memory font '(.+)'$/.exec(body);
    if (match) return `Aviso subtitulos: no se pudo abrir la fuente ${match[1]}`;
    match = /^Using font provider (.+)$/.exec(body);
    if (match) return `Subtitulos: proveedor de fuentes ${match[1]}`;
    match = /^Added subtitle file: '(.+)' \((\d+) styles?, (\d+) events?\)$/.exec(body);
    if (match) return `Subtitulos cargados: ${match[3]} eventos, ${match[2]} estilos`;
    match = /^fontselect: .* -> ([^,]+),/.exec(body);
    if (match) return `Fuente elegida: ${match[1].trim()}`;
    return `Subtitulos: ${body}`;
  }

  if (/^\[swscaler/.test(line)) {
    return `Aviso FFmpeg: formato de pixel heredado; se ajusta durante el render`;
  }

  if (/^\[aist#/.test(line)) {
    return `Audio entrada: ${cleanFfmpegPrefix(line)}`;
  }

  if (/^\[mp4 /.test(line) && /Starting second pass/i.test(line)) {
    return "MP4: finalizando archivo para reproduccion rapida";
  }

  if (/^\[out#/.test(line)) {
    return `Resumen FFmpeg: ${cleanFfmpegPrefix(line)}`;
  }

  if (/^\[aac /.test(line)) {
    return `Audio AAC: ${cleanFfmpegPrefix(line)}`;
  }

  return null;
}

function formatProgressLine(rawLine: string): string | null {
  const line = normalizeLogLine(rawLine).trim();
  if (!line) return "";
  if (extractFfmpegFrameFields(line)) return null;
  if (isFfmpegDetailLine(line)) return null;

  const technicalLine = formatTechnicalProgressLine(line);
  if (technicalLine) return technicalLine;

  let match = /^\[runner\]\s+User override: provider=([^,\s]+), model=(.+)$/.exec(line);
  if (match) return `IA: ${providerLabel(match[1])} (${match[2].trim()})`;

  match = /^\[runner\]\s+User override: provider=([^\s]+)\s+\(no model\)$/.exec(line);
  if (match) return `IA: ${providerLabel(match[1])}`;

  match = /^\[runner\]\s+Using\s+(.+?)\s+provider$/i.exec(line);
  if (match) return `IA: ${providerLabel(match[1])}`;

  match = /^\[runner\]\s+Override: short_render_profile=(.+)$/.exec(line);
  if (match) return `Calidad de render: ${match[1]}`;

  match = /^\[runner\]\s+Override: script_sentence_length=(\d+)$/.exec(line);
  if (match) return `Longitud de frases: ${match[1]} palabras aprox.`;

  match = /^\[runner\]\s+Override: hook_style=(.+)$/.exec(line);
  if (match) return `Estilo de gancho: ${match[1]}`;

  match = /^\[runner\]\s+Retention mode:\s*(.+)$/.exec(line);
  if (match) return `Modo de retencion: ${match[1]}`;

  match = /^\[runner\]\s+Initializing channel '(.+)'$/.exec(line);
  if (match) return `Canal: ${match[1]}`;

  match = /^\[runner\]\s+Hook profile override:\s*(.+)$/.exec(line);
  if (match) return `Perfil de gancho: ${match[1]}`;

  match = /^\[runner\]\s+Generating (SHORT|LONG video) from (\d+) uploaded photo\(s\)\. Topic:\s*(.+)$/.exec(line);
  if (match) {
    const kind = match[1] === "SHORT" ? "Short" : "video largo";
    return `Generando ${kind} con ${match[2]} fotos - ${describeTopic(match[3])}`;
  }

  match = /^\[runner\]\s+Generating (SHORT|LONG video)\. Topic:\s*(.+?)(?:,\s*image_mode=(.+))?$/.exec(line);
  if (match) {
    const kind = match[1] === "SHORT" ? "Short" : "video largo";
    const imageMode = match[3] ? `, imagenes: ${match[3]}` : "";
    return `Generando ${kind} - ${describeTopic(match[2])}${imageMode}`;
  }

  match = /^\[runner\]\s+Generated:\s+(.+)$/.exec(line);
  if (match) return `Archivo generado: ${compactPath(match[1])}`;

  match = /^\[runner\]\s+Social plan ready: quality=([^\s]+)\s+score=([^\s]+)$/.exec(line);
  if (match) return `Plan social listo: calidad=${match[1]}, score=${match[2]}`;

  match = /^\[runner\]\s+Starting upload to (.+)\.\.\.$/.exec(line);
  if (match) return `Subiendo a ${match[1]}...`;

  match = /^\[runner\]\s+Upload results:\s*(.+)$/.exec(line);
  if (match) return `Resultado de subida: ${match[1]}`;

  if (line === "[runner] DONE") return "Proceso terminado";

  match = /^\[runner\]\s+ERROR:\s*(.+)$/.exec(line);
  if (match) return `Error: ${match[1]}`;

  match = /^\[runner\]\s+WARN(?:ING)?:\s*(.+)$/.exec(line);
  if (match) return `Aviso: ${match[1]}`;

  match = /^✅\s+Prepared (\d+) uploaded photos\.$/.exec(line);
  if (match) return `Fotos listas: ${match[1]}`;

  match = /Photo analysis:\s*(.+)$/.exec(line);
  if (match) return `Analisis de fotos: ${match[1]}`;

  match = /Wrote TTS to .+?\((\d+) words timed\)/.exec(line);
  if (match) return `Voz generada: ${match[1]} palabras con tiempos`;

  match = /Short render profile:\s*([^|]+)\|\s*(?:size=([^|]+)\|\s*)?fps=(\d+)\s*\|\s*ken_burns=([^|]+)\|\s*karaoke=([^|]+)\|\s*crossfade=([\d.]+)s/i.exec(line);
  if (match) {
    return [
      `Render Short: ${match[1].trim()}`,
      match[2] ? match[2].trim() : "",
      `${match[3]} fps`,
      `movimiento=${yesNo(match[4].trim())}`,
      `subtitulos=${yesNo(match[5].trim())}`,
      `transicion=${match[6]}s`,
    ].filter(Boolean).join(", ");
  }

  match = /Chose song:\s*([^\s]+)(?:\s+\(.+\))?/.exec(line);
  if (match) return `Musica: ${match[1]}`;

  match = /FFmpeg quality render:\s*fps=(\d+), codec=([^,]+), preset=([^,]+), threads=(\d+), karaoke=(.+)$/i.exec(line);
  if (match) {
    return `Motor de render: ${match[2]}, ${match[1]} fps, ${match[4]} hilos, subtitulos=${yesNo(match[5])}`;
  }

  match = /Wrote Video to "(.+)"$/.exec(line);
  if (match) return `Video listo: ${compactPath(match[1])}`;

  match = /Wrote upload sidecar:\s*(.+)$/.exec(line);
  if (match) return `Metadatos de subida guardados: ${compactPath(match[1])}`;

  match = /Uploaded-photos Short generated:\s*(.+)$/.exec(line);
  if (match) return `Short generado: ${compactPath(match[1])}`;

  match = /Uploaded-photos long video generated:\s*(.+)$/.exec(line);
  if (match) return `Video largo generado: ${compactPath(match[1])}`;

  match = /^\s*\[(Gemini|OpenAI|Ollama|Claude CLI|Codex CLI)\]\s+(.+?)\s+-\s+([\d.]+)s\s+-\s+(.+?)\s+-\s+(\d+)\s+chars$/i.exec(line);
  if (match) return `${match[1]}: respuesta lista en ${match[3]}s (${match[4]})`;

  match = /^\s*\[ok\]\s+Switched to LLM provider:\s*(.+)$/.exec(line);
  if (match) return `Proveedor LLM activo: ${providerLabel(match[1])}`;

  if (/Copying Firefox profile to temp dir/i.test(line)) return "Preparando perfil de Firefox";
  if (/^\[\+\]\s+Combining images/i.test(line)) return "Montando fotos, voz y musica...";
  if (/^\[\+\]\s+Rendering quality Short with ffmpeg/i.test(line)) return "Renderizando video final en calidad alta...";
  if (/^\[\+\]\s+Building karaoke subtitles/i.test(line)) return "Preparando subtitulos...";
  if (/^\[\+\]\s+Karaoke subtitles ready/i.test(line)) return "Subtitulos listos";
  if (/^\[\+\]\s+Mixing audio/i.test(line)) return "Mezclando voz y musica...";

  return line
    .replace(/^\[runner\]\s+/, "")
    .replace(/^(?:ℹ️|✅|⚠️|❌)\s*=>\s*/, "")
    .replace(/^=>\s*/, "")
    .replace(/^\[\+\]\s*/, "");
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
  previewOnFinish = false,
  uploadAfterPreview = false,
  uploadPlatforms = ["youtube"],
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
  const [renderProgress, setRenderProgress] = useState<RenderProgress | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const logBoxRef = useRef<HTMLDivElement | null>(null);
  const lastFfmpegInputTypeRef = useRef("");
  const renderDurationRef = useRef<number | null>(null);
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
  const effectiveUploadPlatforms = useMemo<UploadPlatform[]>(
    () => (uploadPlatforms.length ? uploadPlatforms : ["youtube"]),
    [uploadPlatforms],
  );
  const uploadLabel = useMemo(
    () => formatUploadPlatforms(effectiveUploadPlatforms),
    [effectiveUploadPlatforms],
  );

  // (Re)connect when sseUrl changes (initial open OR upload-last triggered).
  useEffect(() => {
    if (!open || !activeUrl) return;
    setLogs([]);
    setElapsed(0);
    setStatus("running");
    setJobId(null);
    setStickToBottom(true);
    setRenderProgress(null);
    lastFfmpegInputTypeRef.current = "";
    renderDurationRef.current = null;
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
      append("──── proceso iniciado ────");
    });
    es.addEventListener("log", (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent).data);
        if (typeof data.elapsed === "number") setElapsed(data.elapsed);
        const rawLine: string = data.line ?? "";
        const normalizedLine = normalizeLogLine(rawLine).trim();
        const inputType = ffmpegInputType(normalizedLine);
        if (inputType) lastFfmpegInputTypeRef.current = inputType;
        const durationSeconds = detectedDurationSeconds(normalizedLine);
        if (
          durationSeconds &&
          durationSeconds > 1 &&
          lastFfmpegInputTypeRef.current === "wav"
        ) {
          renderDurationRef.current = durationSeconds;
        }
        const frameProgress = parseFfmpegFrameProgress(normalizedLine, renderDurationRef.current);
        if (frameProgress) {
          setRenderProgress(frameProgress);
          return;
        }
        const m = /\[runner\]\s+Generated:\s+(.+)$/.exec(rawLine);
        if (m) {
          const full = m[1].trim();
          const name = full.replace(/^.*[\\/]/, "");
          setGeneratedFile(name);
        }
        const line = formatProgressLine(rawLine);
        if (line !== null) append(line);
      } catch {
        const rawLine = (ev as MessageEvent).data;
        const frameProgress = parseFfmpegFrameProgress(
          normalizeLogLine(rawLine).trim(),
          renderDurationRef.current,
        );
        if (frameProgress) {
          setRenderProgress(frameProgress);
          return;
        }
        const line = formatProgressLine(rawLine);
        if (line !== null) append(line);
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
      setRenderProgress((prev) => prev ? { ...prev, done: true, percent: 100 } : prev);
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
      setRenderProgress(null);
      lastFfmpegInputTypeRef.current = "";
      renderDurationRef.current = null;
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
    setActiveUrl(api.uploadLastUrl(channelId, kind, effectiveUploadPlatforms));
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
                    {phase === "upload" ? `Subiendo a ${uploadLabel}` : title}
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
              <div className="flex items-center gap-2 text-[11px] font-mono uppercase">
                <Terminal className="h-3 w-3" />
                <span>progreso</span>
                {logs.length > 0 && (
                  <span className="text-emerald-200/40 normal-case tracking-normal">
                    · {logs.length} eventos
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
                <span className="text-[10px] font-mono uppercase">
                  {status === "running" ? "live" : status === "done" ? "ready" : status === "error" ? "failed" : "idle"}
                </span>
              </div>
            </div>

            {renderProgress && (
              <RenderProgressBar progress={renderProgress} />
            )}

            <div
              ref={logBoxRef}
              onScroll={handleLogScroll}
              className={`font-mono text-[12px] leading-relaxed bg-[hsl(var(--ink))] text-emerald-200 rounded-b-lg border hairline-strong p-4 overflow-auto scrollbar-thin ${
                renderProgress ? "h-[348px]" : "h-[420px]"
              }`}
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
                  {status === "error" && phase === "upload" ? "Reintentar subida" : `Subir a ${uploadLabel}`}
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
                ? `Al cerrar, se inicia la subida a ${uploadLabel}.`
                : `Revisa el render antes de subirlo a ${uploadLabel}.`}
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

function RenderProgressBar({ progress }: { progress: RenderProgress }) {
  const percent = clampPercent(progress.percent);
  const percentLabel = `${Math.round(percent)}%`;
  return (
    <div className="border-x hairline-strong bg-[hsl(var(--ink))] px-4 pb-3 pt-2 text-emerald-200">
      <div className="flex items-center justify-between gap-3 text-[11px] font-mono">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              progress.done ? "bg-success" : "bg-primary animate-pulse"
            }`}
          />
          <span className="uppercase tracking-wide text-emerald-200/75">
            {progress.done ? "render listo" : "renderizando"}
          </span>
          <span className="text-emerald-200/45 truncate">
            {progress.time} / {progress.durationLabel}
          </span>
        </div>
        <span className="tabular-nums text-emerald-100">{percentLabel}</span>
      </div>

      <div className="mt-2 h-2 overflow-hidden rounded-sm bg-emerald-950/70 ring-1 ring-emerald-300/10">
        <div
          className="h-full rounded-sm bg-gradient-to-r from-lime-300 via-emerald-300 to-sky-300 transition-[width] duration-300 ease-out"
          style={{ width: `${percent}%` }}
        />
      </div>

      <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[10px] font-mono text-emerald-200/60 sm:grid-cols-5">
        <span className="tabular-nums">frames {progress.frame}</span>
        <span className="tabular-nums">fps {progress.fps}</span>
        <span className="tabular-nums">speed {progress.speed}</span>
        <span className="tabular-nums">size {progress.size}</span>
        <span className="tabular-nums">bitrate {progress.bitrate}</span>
      </div>
    </div>
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

function formatUploadPlatforms(platforms: UploadPlatform[]) {
  const labels: Record<UploadPlatform, string> = {
    youtube: "YouTube",
    tiktok: "TikTok",
    facebook: "Facebook",
  };
  const selected = platforms.map((p) => labels[p] ?? p);
  if (selected.length <= 1) return selected[0] || "YouTube";
  return selected.slice(0, -1).join(", ") + " y " + selected[selected.length - 1];
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
      <span className={`text-[10px] font-mono uppercase ${tone.split(" ")[0]}`}>
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
  if (l.includes("warning") || l.includes("aviso") || l.includes("⚠")) return "text-amber-300";
  if (
    l.includes("success") ||
    l.includes("✅") ||
    l.includes("uploaded") ||
    l.includes("listo") ||
    l.includes("generado") ||
    l.includes("terminado")
  ) return "text-emerald-300";
  if (l.startsWith("ia:") || l.startsWith("canal:") || l.startsWith("perfil de gancho:")) return "text-sky-300";
  if (l.startsWith("render") || l.startsWith("motor de render")) return "text-lima";
  if (l.startsWith("entrada") || l.startsWith("salida") || l.startsWith("video #") || l.startsWith("audio #")) return "text-sky-300/90";
  if (l.startsWith("mapa") || l.startsWith("metadata") || l.startsWith("encoder")) return "text-emerald-200/70";
  if (l.startsWith("subtitulos") || l.startsWith("fuente")) return "text-violet-300";
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
