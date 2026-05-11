import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Sparkles,
  ChevronDown,
  Check,
  Play,
  Cpu,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { ProgressDialog } from "@/components/ProgressDialog";
import {
  api,
  SHORT_DURATION_OPTIONS,
  type Channel,
  type SeriesEntry,
  type ShortDurationSeconds,
  type SystemInfo,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

export function Generate() {
  const [params] = useSearchParams();
  const presetChannel = params.get("channel") || "";

  const [channels, setChannels] = useState<Channel[]>([]);
  const [series, setSeries] = useState<SeriesEntry[]>([]);
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [channelId, setChannelId] = useState(presetChannel);
  const [kind, setKind] = useState<"short" | "long">("short");
  const [topic, setTopic] = useState("");
  const [imageMode, setImageMode] = useState<"ai" | "photos">("ai");
  const [seriesId, setSeriesId] = useState("");
  const [autoUpload, setAutoUpload] = useState(false);
  const [previewAtEnd, setPreviewAtEnd] = useState(false);
  const [shortDuration, setShortDuration] = useState<ShortDurationSeconds>(60);

  // Decorative mixer knobs — not wired to the backend. They make the panel
  // feel like a control surface; the actual TTS/BSO volumes live in
  // config.json (Audio section). Leaving them as state so future work can
  // forward them as job-level overrides.
  const [voiceVol, setVoiceVol] = useState(85);
  const [musicVol, setMusicVol] = useState(35);
  const [pace, setPace] = useState(50);
  const [seed, setSeed] = useState("");

  const [llmProvider, setLlmProvider] = useState<"" | "ollama" | "gemini">("");
  const [llmModel, setLlmModel] = useState<string>("");
  const [llmModels, setLlmModels] = useState<{
    ollama: string[];
    gemini: string[];
    errors: Record<string, string>;
  }>({ ollama: [], gemini: [], errors: {} });

  const [progressOpen, setProgressOpen] = useState(false);
  const [sseUrl, setSseUrl] = useState<string | null>(null);

  useEffect(() => {
    api
      .listChannels()
      .then((d) => {
        setChannels(d);
        if (!channelId && d.length > 0) setChannelId(d[0].id);
      })
      .catch(() => {});
    api.listSeries().then(setSeries).catch(() => {});
    api.systemInfo().then(setInfo).catch(() => {});
    api.listLlmModels().then(setLlmModels).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!llmProvider) {
      setLlmModel("");
      return;
    }
    const list = llmProvider === "ollama" ? llmModels.ollama : llmModels.gemini;
    if (list.length === 0) setLlmModel("");
    else if (!list.includes(llmModel)) setLlmModel(list[0]);
  }, [llmProvider, llmModels, llmModel]);

  const selectedChannel = useMemo(
    () => channels.find((c) => c.id === channelId),
    [channels, channelId],
  );

  // Filter series to those belonging to the selected channel — when the API
  // doesn't expose a channel link on series, fall back to all series.
  const channelSeries = useMemo(() => {
    if (!series.length) return [];
    // SeriesEntry doesn't expose channel — until it does, show all so the user
    // can still pick one.
    return series;
  }, [series]);

  const start = () => {
    if (!channelId) {
      toast.error("Selecciona un canal");
      return;
    }
    const serverAutoUpload = autoUpload && !previewAtEnd;
    const url = api.generateUrl(channelId, {
      kind,
      custom_topic: topic.trim(),
      image_mode: imageMode,
      auto_upload: serverAutoUpload,
      series_id: seriesId || undefined,
      duration_seconds: kind === "short" ? shortDuration : undefined,
      llm_provider: llmProvider || undefined,
      llm_model: llmProvider && llmModel ? llmModel : undefined,
    });
    setSseUrl(url);
    setProgressOpen(true);
  };

  const eta = kind === "short"
    ? Math.round(shortDuration * 0.18 + 90)
    : 900;

  return (
    <>
      <Header
        eyebrow="· estudio"
        title="Generar contenido"
        description="Pipeline LLM → TTS → imagen → render"
      />

      <PageShell>
        <div
          className="grid gap-3.5"
          style={{ gridTemplateColumns: "minmax(0, 1fr) 360px" }}
        >
          {/* MAIN — 3-stage console */}
          <div
            className="studio-surface overflow-hidden"
            style={{ background: "hsl(var(--card))" }}
          >
            {/* Track headers */}
            <div
              className="grid grid-cols-3"
              style={{ borderBottom: "1px solid hsl(var(--border) / .07)" }}
            >
              <TrackHeader
                num="01"
                label="INPUT"
                desc="Qué quieres contar"
                colorVar="var(--primary)"
                rightBorder
              />
              <TrackHeader
                num="02"
                label="TRANSFORM"
                desc="Cómo se construye"
                colorVar="var(--accent)"
                rightBorder
              />
              <TrackHeader
                num="03"
                label="OUTPUT"
                desc="Dónde aterriza"
                colorVar="var(--gold)"
              />
            </div>

            {/* Track bodies */}
            <div className="grid grid-cols-3">
              {/* INPUT */}
              <div
                className="px-[18px] pt-[18px] pb-[22px] flex flex-col gap-3.5"
                style={{ borderRight: "1px solid hsl(var(--border) / .07)" }}
              >
                <Field label="Canal">
                  <ChannelSelect
                    channels={channels}
                    value={channelId}
                    onChange={setChannelId}
                  />
                </Field>
                <Field label="Formato">
                  <Segmented
                    value={kind}
                    onChange={(v) => setKind(v as "short" | "long")}
                    accentVar="var(--primary)"
                    options={[
                      { value: "short", label: "Short · 9:16" },
                      { value: "long", label: "Long · 16:9" },
                    ]}
                  />
                </Field>
                <Field label="Tema" hint={`${topic.length} chars`}>
                  <TextArea
                    value={topic}
                    onChange={setTopic}
                    placeholder="Déjalo vacío para que el LLM elija un tema según el niche del canal"
                    rows={3}
                  />
                </Field>
                {kind === "long" && channelSeries.length > 0 && (
                  <Field label="Serie (opcional)">
                    <Segmented
                      value={seriesId}
                      onChange={setSeriesId}
                      accentVar="var(--primary)"
                      options={[
                        { value: "", label: "Ninguna" },
                        ...channelSeries.map((s) => ({
                          value: s.id,
                          label: s.name || s.id,
                        })),
                      ]}
                    />
                  </Field>
                )}
              </div>

              {/* TRANSFORM */}
              <div
                className="px-[18px] pt-[18px] pb-[22px] flex flex-col gap-[18px]"
                style={{ borderRight: "1px solid hsl(var(--border) / .07)" }}
              >
                {kind === "short" && (
                  <Field label="Duración">
                    <Segmented
                      value={String(shortDuration)}
                      onChange={(v) =>
                        setShortDuration(Number(v) as ShortDurationSeconds)
                      }
                      accentVar="var(--accent)"
                      options={SHORT_DURATION_OPTIONS.map((s) => ({
                        value: String(s),
                        label: `${s}s`,
                      }))}
                    />
                  </Field>
                )}
                <Field label="Fuente de imágenes">
                  <Segmented
                    value={imageMode}
                    onChange={(v) => setImageMode(v as "ai" | "photos")}
                    accentVar="var(--accent)"
                    options={[
                      { value: "ai", label: "AI · Nano Banana" },
                      { value: "photos", label: "Stock fotos" },
                    ]}
                  />
                </Field>

                <div
                  className="rounded-[10px] px-3 py-3.5 flex items-center justify-around gap-1.5"
                  style={{
                    background: "hsl(var(--background))",
                    border: "1px solid hsl(var(--border) / .07)",
                  }}
                >
                  <Knob
                    label="VOZ"
                    value={voiceVol}
                    onChange={setVoiceVol}
                    suffix="%"
                    accentVar="var(--accent)"
                  />
                  <Knob
                    label="BSO"
                    value={musicVol}
                    onChange={setMusicVol}
                    suffix="%"
                    accentVar="var(--accent)"
                  />
                  <Knob
                    label="RITMO"
                    value={pace}
                    onChange={setPace}
                    suffix=""
                    accentVar="var(--accent)"
                  />
                </div>

                <Field label="Estilo de imagen" hint="del canal">
                  <div
                    className="rounded-lg px-3 py-2 text-[11.5px] leading-relaxed font-mono text-muted-foreground"
                    style={{
                      background: "hsl(var(--background))",
                      border: "1px solid hsl(var(--border) / .07)",
                    }}
                  >
                    {selectedChannel?.image_style ||
                      "(default — no se inyecta estilo)"}
                  </div>
                </Field>
              </div>

              {/* OUTPUT */}
              <div className="px-[18px] pt-[18px] pb-[22px] flex flex-col gap-1.5">
                <Field label="Seed (reproducible)">
                  <TextInput
                    value={seed}
                    onChange={setSeed}
                    placeholder="(opcional)"
                    mono
                  />
                </Field>

                {/* LLM model override (compact) */}
                <Field
                  label="LLM"
                  hint={llmProvider || "auto"}
                >
                  <div className="flex gap-1.5">
                    <SelectMini
                      value={llmProvider || "auto"}
                      onChange={(v) =>
                        setLlmProvider(
                          v === "auto" ? "" : (v as "ollama" | "gemini"),
                        )
                      }
                      options={[
                        { value: "auto", label: "Auto" },
                        {
                          value: "ollama",
                          label: `Ollama${
                            llmModels.ollama.length
                              ? ` (${llmModels.ollama.length})`
                              : ""
                          }`,
                        },
                        {
                          value: "gemini",
                          label: `Gemini${
                            llmModels.gemini.length
                              ? ` (${llmModels.gemini.length})`
                              : ""
                          }`,
                        },
                      ]}
                      icon={<Cpu className="h-3 w-3" strokeWidth={1.5} />}
                    />
                    {llmProvider && (
                      <SelectMini
                        value={llmModel}
                        onChange={setLlmModel}
                        options={(llmProvider === "ollama"
                          ? llmModels.ollama
                          : llmModels.gemini
                        ).map((m) => ({ value: m, label: m }))}
                      />
                    )}
                  </div>
                </Field>

                <ToggleRow
                  label="Auto-subir a YouTube"
                  hint="Selenium contra YouTube Studio al terminar el render"
                  value={autoUpload}
                  onChange={setAutoUpload}
                />
                <Divider />
                <ToggleRow
                  label="Preview al final"
                  hint="Muestra modal con el vídeo antes de subir"
                  value={previewAtEnd}
                  onChange={setPreviewAtEnd}
                />

                <div className="mt-auto pt-[18px]">
                  <Button
                    variant="brand"
                    size="lg"
                    className="w-full gap-2"
                    onClick={start}
                    disabled={!channelId}
                  >
                    <Play className="h-3.5 w-3.5" /> Imprimir vídeo
                  </Button>
                  <div className="mt-2.5 flex items-center justify-between text-[11px] text-muted-foreground font-mono">
                    <span>ETA ~{eta}s</span>
                    <span>
                      · {kind === "short" ? "1080×1920" : "1920×1080"} · 30fps
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer signal strip */}
            <div
              className="flex items-center gap-3.5 px-5 py-2.5 font-mono text-[11px] text-muted-foreground"
              style={{
                borderTop: "1px solid hsl(var(--border) / .07)",
                background: "hsl(var(--background))",
              }}
            >
              <span style={{ color: "hsl(var(--success))" }}>● online</span>
              <span className="text-muted-foreground">·</span>
              <span>llm: {info?.llm_provider || "—"}</span>
              <span className="text-muted-foreground">·</span>
              <span>tts: {info?.tts_voice || "—"}</span>
              <span className="text-muted-foreground">·</span>
              <span>img: nano-banana-2</span>
              <span className="ml-auto text-muted-foreground">
                {info?.headless ? "headless" : "headful"} ·{" "}
                {info?.image_aspect_ratio || "9:16"}
              </span>
            </div>
          </div>

          {/* SIDE — channel summary + tips */}
          <div className="flex flex-col gap-3.5">
            <ChannelSummary channel={selectedChannel} />
            <TipsCard />
          </div>
        </div>
      </PageShell>

      <ProgressDialog
        open={progressOpen}
        onOpenChange={setProgressOpen}
        title={kind === "short" ? "Generando short" : "Generando vídeo largo"}
        description={
          autoUpload && previewAtEnd
            ? "Render → preview al terminar → subida al cerrar el preview."
            : autoUpload
            ? "Render + upload automático al terminar."
            : previewAtEnd
            ? "Render → preview al terminar para que lo revises."
            : "Solo render — al terminar puedes revisar y subir desde aquí."
        }
        sseUrl={sseUrl}
        channelId={autoUpload && !previewAtEnd ? undefined : channelId}
        kind={kind}
        previewOnFinish={previewAtEnd}
        uploadAfterPreview={autoUpload && previewAtEnd}
      />
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Track header
// ─────────────────────────────────────────────────────────────────────────────
function TrackHeader({
  num,
  label,
  desc,
  colorVar,
  rightBorder,
}: {
  num: string;
  label: string;
  desc: string;
  colorVar: string;
  rightBorder?: boolean;
}) {
  return (
    <div
      className="px-[18px] py-3.5 relative"
      style={{
        borderRight: rightBorder ? "1px solid hsl(var(--border) / .07)" : "none",
      }}
    >
      <span
        aria-hidden
        className="absolute top-0 left-0 right-0 h-0.5"
        style={{ background: `hsl(${colorVar})`, opacity: 0.7 }}
      />
      <div className="flex items-center gap-2 mb-0.5">
        <span
          className="font-mono text-[10px] font-semibold"
          style={{ letterSpacing: "0.16em", color: `hsl(${colorVar})` }}
        >
          · {num}
        </span>
        <span
          className="font-mono uppercase font-semibold text-[10px]"
          style={{ letterSpacing: "0.24em", color: `hsl(${colorVar})` }}
        >
          {label}
        </span>
      </div>
      <div className="text-[11.5px] text-muted-foreground">{desc}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Form primitives
// ─────────────────────────────────────────────────────────────────────────────
function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="flex items-center justify-between text-[11px] text-muted-foreground font-medium tracking-tight">
        <span>{label}</span>
        {hint && (
          <span className="font-mono text-[10px] text-muted-foreground/80">
            {hint}
          </span>
        )}
      </label>
      {children}
    </div>
  );
}

function TextInput({
  value,
  onChange,
  placeholder,
  mono,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  mono?: boolean;
}) {
  return (
    <input
      type="text"
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "w-full h-9 px-3 rounded-lg outline-none text-foreground text-[13px]",
        mono && "font-mono",
      )}
      style={{
        background: "hsl(var(--background))",
        border: "1px solid hsl(var(--border) / .07)",
        transition: "border-color 120ms ease",
      }}
      onFocus={(e) => (e.target.style.borderColor = "hsl(var(--primary) / .35)")}
      onBlur={(e) => (e.target.style.borderColor = "hsl(var(--border) / .07)")}
    />
  );
}

function TextArea({
  value,
  onChange,
  placeholder,
  rows = 3,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
}) {
  return (
    <textarea
      value={value}
      placeholder={placeholder}
      rows={rows}
      onChange={(e) => onChange(e.target.value)}
      className="w-full px-3 py-2 rounded-lg outline-none text-foreground text-[13px] resize-y"
      style={{
        background: "hsl(var(--background))",
        border: "1px solid hsl(var(--border) / .07)",
        transition: "border-color 120ms ease",
      }}
      onFocus={(e) => (e.target.style.borderColor = "hsl(var(--primary) / .35)")}
      onBlur={(e) => (e.target.style.borderColor = "hsl(var(--border) / .07)")}
    />
  );
}

function Segmented({
  options,
  value,
  onChange,
  accentVar,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
  accentVar: string;
}) {
  return (
    <div
      className="inline-flex rounded-lg p-[3px] gap-0.5"
      style={{
        background: "hsl(var(--background))",
        border: "1px solid hsl(var(--border) / .07)",
      }}
    >
      {options.map((opt) => {
        const active = value === opt.value;
        return (
          <button
            key={opt.value || "_"}
            type="button"
            onClick={() => onChange(opt.value)}
            className={cn(
              "px-3 py-1.5 rounded-md text-[12px] cursor-pointer tracking-tight",
              active
                ? "bg-surface text-foreground font-medium"
                : "bg-transparent text-muted-foreground hover:text-foreground",
            )}
            style={{
              boxShadow: active
                ? `inset 0 0 0 1px color-mix(in oklch, hsl(${accentVar}) 30%, transparent)`
                : "none",
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function ToggleRow({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-2.5 py-2">
      <div className="flex-1">
        <div className="text-[13px] text-foreground font-medium tracking-tight">
          {label}
        </div>
        {hint && (
          <div className="text-[11.5px] text-muted-foreground mt-0.5">
            {hint}
          </div>
        )}
      </div>
      <Switch checked={value} onCheckedChange={onChange} />
    </div>
  );
}

function Divider() {
  return (
    <div
      className="h-px"
      style={{ background: "hsl(var(--border) / .04)" }}
    />
  );
}

function SelectMini({
  value,
  onChange,
  options,
  icon,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  icon?: React.ReactNode;
}) {
  return (
    <div className="relative flex-1 min-w-0">
      {icon && (
        <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none">
          {icon}
        </span>
      )}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "w-full h-9 rounded-lg outline-none text-foreground text-[12px] font-mono appearance-none cursor-pointer truncate",
          icon ? "pl-8 pr-7" : "px-3 pr-7",
        )}
        style={{
          background: "hsl(var(--background))",
          border: "1px solid hsl(var(--border) / .07)",
        }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown
        className="h-3 w-3 text-muted-foreground absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
        strokeWidth={1.5}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Knob
// ─────────────────────────────────────────────────────────────────────────────
function Knob({
  label,
  value,
  onChange,
  min = 0,
  max = 100,
  suffix = "",
  accentVar,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  suffix?: string;
  accentVar: string;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  const angle = -135 + (pct / 100) * 270;

  // Wheel scroll adjusts the knob in 5% steps. Click + drag isn't worth the
  // complexity for a decorative control.
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -5 : 5;
    onChange(Math.max(min, Math.min(max, value + delta)));
  };

  return (
    <div className="flex flex-col items-center gap-1.5" style={{ minWidth: 64 }}>
      <div
        onWheel={handleWheel}
        className="relative rounded-full cursor-pointer"
        style={{
          width: 56,
          height: 56,
          background: "hsl(var(--background))",
          border: "1px solid hsl(var(--border) / .07)",
          boxShadow:
            "inset 0 1px 0 hsl(var(--border) / .04), 0 2px 8px rgba(0,0,0,0.3)",
        }}
        title={`${label} — scroll para ajustar`}
      >
        <svg width="56" height="56" className="absolute inset-0">
          <circle
            cx="28"
            cy="28"
            r="22"
            fill="none"
            stroke="hsl(var(--surface-up))"
            strokeWidth="2.5"
            strokeDasharray="103.6 138"
            strokeDashoffset="34.5"
            transform="rotate(135 28 28)"
            strokeLinecap="round"
          />
          <circle
            cx="28"
            cy="28"
            r="22"
            fill="none"
            stroke={`hsl(${accentVar})`}
            strokeWidth="2.5"
            strokeDasharray={`${pct * 1.036} 138`}
            strokeDashoffset="34.5"
            transform="rotate(135 28 28)"
            strokeLinecap="round"
          />
        </svg>
        <div
          className="absolute top-1/2 left-1/2 rounded-sm"
          style={{
            width: 2,
            height: 13,
            background: `hsl(${accentVar})`,
            transform: `translate(-50%, -100%) rotate(${angle}deg)`,
            transformOrigin: "50% 100%",
          }}
        />
      </div>
      <span className="font-mono text-[11.5px] text-foreground tabular-nums">
        {value}
        {suffix}
      </span>
      <span
        className="font-mono uppercase text-[9.5px] text-muted-foreground"
        style={{ letterSpacing: "0.16em" }}
      >
        {label}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ChannelSelect — custom dropdown with avatar + lang/uploads sub-line
// ─────────────────────────────────────────────────────────────────────────────
function ChannelSelect({
  channels,
  value,
  onChange,
}: {
  channels: Channel[];
  value: string;
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ch = channels.find((c) => c.id === value) || channels[0];

  if (!channels.length) {
    return (
      <div
        className="h-11 px-3 rounded-lg flex items-center text-[13px] text-muted-foreground"
        style={{
          background: "hsl(var(--background))",
          border: "1px solid hsl(var(--border) / .07)",
        }}
      >
        No hay canales — crea uno primero
      </div>
    );
  }

  const initial = (ch?.nickname || "?").slice(0, 1).toUpperCase();

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full h-11 px-3 rounded-lg flex items-center gap-2.5 text-foreground text-left"
        style={{
          background: "hsl(var(--background))",
          border: "1px solid hsl(var(--border) / .07)",
        }}
      >
        <span
          className="w-[26px] h-[26px] rounded-md flex items-center justify-center font-display font-bold text-[11px] shrink-0"
          style={{
            background: "hsl(var(--primary) / .14)",
            border: "1px solid hsl(var(--primary) / .35)",
            color: "hsl(var(--primary))",
          }}
        >
          {initial}
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-medium leading-tight tracking-tight truncate">
            {ch?.nickname}
          </div>
          <div className="text-[10.5px] text-muted-foreground font-mono truncate">
            {ch?.language || "—"} · {ch?.videos_count} subidas
          </div>
        </div>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
      </button>

      {open && (
        <div
          onMouseLeave={() => setOpen(false)}
          className="absolute left-0 right-0 top-[calc(100%+6px)] z-30 rounded-[10px] p-1.5 max-h-[280px] overflow-auto scrollbar-thin"
          style={{
            background: "hsl(var(--card))",
            border: "1px solid hsl(var(--border) / .07)",
            boxShadow: "0 24px 60px -20px rgba(0,0,0,0.55)",
          }}
        >
          {channels.map((c) => {
            const active = c.id === value;
            const i = (c.nickname || "?").slice(0, 1).toUpperCase();
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => {
                  onChange(c.id);
                  setOpen(false);
                }}
                className={cn(
                  "flex items-center gap-2.5 w-full px-2.5 py-2 rounded-md text-left text-foreground",
                  active ? "bg-surface" : "hover:bg-surface",
                )}
              >
                <span
                  className="w-6 h-6 rounded-md flex items-center justify-center font-display font-bold text-[11px] shrink-0"
                  style={{
                    background: "hsl(var(--primary) / .14)",
                    border: "1px solid hsl(var(--primary) / .35)",
                    color: "hsl(var(--primary))",
                  }}
                >
                  {i}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-[12.5px] font-medium truncate">{c.nickname}</div>
                  <div className="text-[10.5px] text-muted-foreground font-mono truncate">
                    {c.niche || "—"} · {c.videos_count} vids
                  </div>
                </div>
                {active && <Check className="h-3.5 w-3.5 text-primary" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Side panel cards
// ─────────────────────────────────────────────────────────────────────────────
function ChannelSummary({ channel }: { channel: Channel | undefined }) {
  if (!channel) {
    return (
      <div
        className="studio-surface px-[18px] py-4"
        style={{ background: "hsl(var(--card))" }}
      >
        <span className="eyebrow text-muted-foreground">Canal seleccionado</span>
        <div className="mt-2 text-[13px] text-muted-foreground">
          Selecciona un canal para ver detalles.
        </div>
      </div>
    );
  }

  return (
    <div
      className="studio-surface relative overflow-hidden px-[18px] py-[18px]"
      style={{ background: "hsl(var(--card))" }}
    >
      <span
        aria-hidden
        className="absolute top-0 left-0 right-0 h-[3px]"
        style={{ background: "hsl(var(--primary))" }}
      />
      <span
        className="eyebrow block mb-2.5"
        style={{ color: "hsl(var(--primary))" }}
      >
        Canal seleccionado
      </span>
      <h3 className="font-display text-[22px] font-semibold tracking-[-0.02em] mb-1">
        {channel.nickname}
      </h3>
      <div className="text-[12px] text-muted-foreground mb-3.5">
        {channel.niche || "(sin niche)"} · {channel.language || "—"}
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3.5">
        <Mini label="Idioma" value={channel.language || "es"} accentVar="var(--primary)" />
        <Mini
          label="Vídeos"
          value={String(channel.videos_count)}
          accentVar="var(--accent)"
        />
      </div>

      <div className="flex flex-col gap-2 text-[11.5px]">
        <Row k="Voz Short" v={channel.short_voice || "default"} />
        <Row k="Voz Long" v={channel.long_voice || "default"} />
        <Row k="Estilo" v={channel.image_style || "default"} />
      </div>
    </div>
  );
}

function Mini({
  label,
  value,
  accentVar,
}: {
  label: string;
  value: string;
  accentVar: string;
}) {
  return (
    <div
      className="rounded-lg px-3 py-2.5"
      style={{
        background: "hsl(var(--background))",
        border: "1px solid hsl(var(--border) / .07)",
      }}
    >
      <span
        className="font-mono uppercase font-semibold text-[9px] tracking-[0.20em]"
        style={{ color: `hsl(${accentVar})` }}
      >
        {label}
      </span>
      <div
        className="font-display text-[18px] font-semibold tracking-[-0.02em] mt-0.5 truncate"
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
        {value}
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <span
        className="font-mono uppercase text-[10px] text-muted-foreground"
        style={{ letterSpacing: "0.10em" }}
      >
        {k}
      </span>
      <span className="font-mono text-[11px] text-foreground truncate max-w-[180px]">
        {v}
      </span>
    </div>
  );
}

function TipsCard() {
  return (
    <div
      className="studio-surface px-[18px] py-[18px]"
      style={{ background: "hsl(var(--card))" }}
    >
      <span className="eyebrow text-muted-foreground block mb-2.5">Tips</span>
      <ul className="m-0 pl-4 flex flex-col gap-2 text-[12px] text-muted-foreground leading-relaxed">
        <li>
          <strong className="text-foreground font-medium">
            Tema corto y específico
          </strong>{" "}
          rinde mejor en Shorts (≤ 80 chars).
        </li>
        <li>
          Si activas{" "}
          <strong className="text-foreground font-medium">auto-subir</strong>, el
          render usa el perfil Firefox del canal.
        </li>
        <li>
          El modo{" "}
          <strong className="text-foreground font-medium">Stock fotos</strong>{" "}
          busca primero en Wikipedia/Wikimedia/Europeana antes de generar con AI.
        </li>
        <li>
          La subida usa{" "}
          <strong className="text-foreground font-medium">Selenium</strong> contra
          YouTube Studio. El perfil Firefox debe estar pre-loggeado.
        </li>
      </ul>
    </div>
  );
}
