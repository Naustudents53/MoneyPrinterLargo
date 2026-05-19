import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Sparkles,
  ChevronDown,
  Check,
  Play,
  Cpu,
  Eye,
  Layers,
  Lightbulb,
  Loader2,
  X,
  Upload,
  Youtube,
  Music2,
  Facebook,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { ProgressDialog } from "@/components/ProgressDialog";
import { ScriptPreviewDialog } from "@/components/ScriptPreviewDialog";
import { BatchGenerateDialog } from "@/components/BatchGenerateDialog";
import {
  api,
  RETENTION_MODE_OPTIONS,
  SHORT_DURATION_OPTIONS,
  HOOK_PROFILE_OPTIONS,
  SHORT_RENDER_PROFILE_OPTIONS,
  type Channel,
  type ClaudeReasoningEffort,
  type HookProfile,
  type ImageProvider,
  type LLMRunMode,
  type LLMProvider,
  type LLMModel,
  type LLMReasoningEffort,
  type OpenAIReasoningEffort,
  type SeriesEntry,
  type ShortDurationSeconds,
  type ShortRenderProfile,
  type RetentionMode,
  type SystemInfo,
  type UploadPlatform,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const SHORT_RENDER_META: Record<ShortRenderProfile, {
  label: string;
  hint: string;
  fps: number;
}> = {
  quality: { label: "Calidad", hint: "Ken Burns + karaoke", fps: 30 },
  fast: { label: "Rápido", hint: "Karaoke, sin zoom", fps: 24 },
  turbo: { label: "Turbo", hint: "Render limpio", fps: 24 },
};

const RETENTION_MODE_META: Record<RetentionMode, {
  label: string;
  hint: string;
}> = {
  standard: { label: "Estandar", hint: "ritmo normal" },
  maxima_retencion: { label: "MAXIMA RETENCION", hint: "hook + cortes" },
};

type VisualSource = "ai" | "photos" | "upload";

const OPENAI_REASONING_OPTIONS: Array<{ value: OpenAIReasoningEffort; label: string }> = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "xhigh", label: "XHigh" },
];

const CLAUDE_REASONING_OPTIONS: Array<{ value: ClaudeReasoningEffort; label: string }> = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "xhigh", label: "XHigh" },
  { value: "max", label: "Max" },
];

const CLAUDE_MODE_OPTIONS: Array<{ value: LLMRunMode; label: string }> = [
  { value: "standard", label: "Estándar" },
  { value: "fast", label: "Fast" },
];

const IMAGE_PROVIDER_OPTIONS: Array<{ value: ImageProvider; label: string }> = [
  { value: "leonardo", label: "Leonardo API" },
  { value: "openai", label: "OpenAI · Codex Image 2" },
  { value: "gemini", label: "Gemini · Nano Banana" },
];

export function Generate() {
  const [params] = useSearchParams();
  const presetChannel = params.get("channel") || "";

  const [channels, setChannels] = useState<Channel[]>([]);
  const [series, setSeries] = useState<SeriesEntry[]>([]);
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [channelId, setChannelId] = useState(presetChannel);
  const [kind, setKind] = useState<"short" | "long">("short");
  const [topic, setTopic] = useState("");
  const [imageMode, setImageMode] = useState<VisualSource>("ai");
  const [photoFiles, setPhotoFiles] = useState<File[]>([]);
  const [uploadingPhotos, setUploadingPhotos] = useState(false);
  const [seriesId, setSeriesId] = useState("");
  // Per-job hook profile override. Empty string = use the channel's configured
  // default (selectedChannel.hook_profile); otherwise overrides for THIS run.
  const [hookProfile, setHookProfile] = useState<HookProfile | "">("");
  const [uploadPlatforms, setUploadPlatforms] = useState<UploadPlatform[]>([]);
  const [previewAtEnd, setPreviewAtEnd] = useState(false);
  const [shortDuration, setShortDuration] = useState<ShortDurationSeconds>(60);
  const [shortRenderProfile, setShortRenderProfile] = useState<ShortRenderProfile>("fast");
  const [retentionMode, setRetentionMode] = useState<RetentionMode>("standard");

  // Decorative mixer knobs — not wired to the backend. They make the panel
  // feel like a control surface; the actual TTS/BSO volumes live in
  // config.json (Audio section). Leaving them as state so future work can
  // forward them as job-level overrides.
  const [voiceVol, setVoiceVol] = useState(85);
  const [musicVol, setMusicVol] = useState(35);
  const [pace, setPace] = useState(50);
  const [seed, setSeed] = useState("");

  const [llmProvider, setLlmProvider] = useState<"" | LLMProvider>("");
  const [llmModel, setLlmModel] = useState<string>("");
  const [openaiReasoningEffort, setOpenaiReasoningEffort] = useState<OpenAIReasoningEffort>("xhigh");
  const [claudeReasoningEffort, setClaudeReasoningEffort] = useState<ClaudeReasoningEffort>("medium");
  const [claudeMode, setClaudeMode] = useState<LLMRunMode>("standard");
  const [imageProvider, setImageProvider] = useState<ImageProvider>("auto");
  // Rich model catalog from /api/llm/models — keeps `label` + `description` so
  // the dropdown can show human-readable names instead of raw ids like
  // "gemini-2.5-flash-lite" or "kimi-k2.6:cloud".
  const [llmCatalog, setLlmCatalog] = useState<LLMModel[]>([]);

  const llmModels = useMemo(() => {
    const buckets: Record<LLMProvider, LLMModel[]> = {
      ollama: [],
      gemini: [],
      openai: [],
      claude: [],
      pollinations: [],
    };
    for (const m of llmCatalog) {
      if (m.provider in buckets) buckets[m.provider].push(m);
    }
    return buckets;
  }, [llmCatalog]);

  const [progressOpen, setProgressOpen] = useState(false);
  const [sseUrl, setSseUrl] = useState<string | null>(null);

  const selectedReasoningEffort: LLMReasoningEffort | undefined =
    llmProvider === "openai"
      ? openaiReasoningEffort
      : llmProvider === "claude"
      ? claudeReasoningEffort
      : undefined;
  const selectedLlmMode: LLMRunMode | undefined = llmProvider === "claude" ? claudeMode : undefined;

  // Script preview flow — opens its own dialog with editable text. After
  // approval, kicks the full /generate flow with `script_file=<previewId>`
  // so the renderer skips re-generating the script.
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewSseUrl, setPreviewSseUrl] = useState<string | null>(null);

  // Batch generation — pop a dialog that lets the user queue jobs across
  // multiple channels in one shot. Independent of the single-job flow above.
  const [batchOpen, setBatchOpen] = useState(false);

  // Topic suggestions — N LLM-generated ideas tailored to the channel's niche
  // that the user can click to fill the topic textarea. Empty list = no
  // suggestions fetched yet; loading flag throttles concurrent calls.
  const [topicIdeas, setTopicIdeas] = useState<string[]>([]);
  const [ideasLoading, setIdeasLoading] = useState(false);

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
    api
      .listLLMModels()
      .then((d) => setLlmCatalog(d.models ?? []))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const profile = info?.short_render_profile;
    if (profile && SHORT_RENDER_PROFILE_OPTIONS.includes(profile)) {
      setShortRenderProfile(profile);
    }
  }, [info?.short_render_profile]);

  useEffect(() => {
    if (!llmProvider) {
      setLlmModel("");
      return;
    }
    const list = llmModels[llmProvider] ?? [];
    if (list.length === 0) setLlmModel("");
    else if (!list.some((m) => m.id === llmModel)) setLlmModel(list[0].id);
  }, [llmProvider, llmModels, llmModel]);

  const showImageProviderSelector = llmProvider === "openai" || llmProvider === "claude";

  useEffect(() => {
    if (showImageProviderSelector) {
      if (imageMode !== "ai") setImageMode("ai");
      if (imageProvider === "auto") {
        setImageProvider(llmProvider === "openai" ? "openai" : "leonardo");
      }
      return;
    }
    if (imageProvider !== "auto") setImageProvider("auto");
  }, [showImageProviderSelector, llmProvider, imageMode, imageProvider]);

  const selectedChannel = useMemo(
    () => channels.find((c) => c.id === channelId),
    [channels, channelId],
  );

  // Filter series to those belonging to the selected channel — when the API
  // doesn't expose a channel link on series, fall back to all series.
  const autoUpload = uploadPlatforms.length > 0;
  const uploadTargetLabel = useMemo(
    () => formatUploadPlatformLabel(uploadPlatforms),
    [uploadPlatforms],
  );

  const toggleUploadPlatform = (platform: UploadPlatform) => {
    setUploadPlatforms((prev) =>
      prev.includes(platform)
        ? prev.filter((item) => item !== platform)
        : [...prev, platform],
    );
  };

  const channelSeries = useMemo(() => {
    if (!series.length) return [];
    // SeriesEntry doesn't expose channel — until it does, show all so the user
    // can still pick one.
    return series;
  }, [series]);

  const uploadSelectedPhotos = async () => {
    if (imageMode !== "upload") return "";
    if (photoFiles.length === 0) {
      toast.error("Selecciona al menos una foto");
      return "";
    }
    setUploadingPhotos(true);
    try {
      const uploaded = await api.uploadPhotos(photoFiles);
      return uploaded.id;
    } finally {
      setUploadingPhotos(false);
    }
  };

  const start = async () => {
    if (!channelId) {
      toast.error("Selecciona un canal");
      return;
    }
    let photoUploadId = "";
    try {
      photoUploadId = await uploadSelectedPhotos();
    } catch (e) {
      toast.error(`No se pudieron subir las fotos: ${(e as Error).message}`);
      return;
    }
    if (imageMode === "upload" && !photoUploadId) return;

    const serverUploadPlatforms = previewAtEnd ? [] : uploadPlatforms;
    const url = api.generateUrl(channelId, {
      kind,
      custom_topic: topic.trim(),
      image_mode: imageMode === "photos" ? "photos" : "ai",
      image_provider: showImageProviderSelector ? imageProvider : undefined,
      auto_upload: serverUploadPlatforms.length > 0,
      upload_platforms: serverUploadPlatforms,
      series_id: seriesId || undefined,
      duration_seconds: kind === "short" ? shortDuration : undefined,
      render_profile: kind === "short" ? shortRenderProfile : undefined,
      llm_provider: llmProvider || undefined,
      llm_model: llmProvider && llmModel ? llmModel : undefined,
      llm_reasoning_effort: selectedReasoningEffort,
      llm_mode: selectedLlmMode,
      hook_profile: hookProfile || undefined,
      photo_upload_id: photoUploadId || undefined,
      retention_mode: kind === "short" ? retentionMode : undefined,
    });
    setSseUrl(url);
    setProgressOpen(true);
  };

  const fetchTopicIdeas = async () => {
    if (!channelId) {
      toast.error("Selecciona un canal");
      return;
    }
    if (ideasLoading) return;
    setIdeasLoading(true);
    try {
      const { topics } = await api.suggestTopics(channelId, {
        n: 6,
        model: llmProvider && llmModel ? llmModel : undefined,
        llm_provider: llmProvider || undefined,
        llm_reasoning_effort: selectedReasoningEffort,
        llm_mode: selectedLlmMode,
      });
      setTopicIdeas(topics || []);
      if (!topics?.length) toast.info("El LLM no devolvió ideas — prueba otro modelo");
    } catch (e) {
      toast.error(`No se pudieron generar ideas: ${(e as Error).message}`);
    } finally {
      setIdeasLoading(false);
    }
  };

  // Re-set the cached ideas whenever the user switches channels — the cached
  // list belongs to the previous niche and would be misleading.
  useEffect(() => {
    setTopicIdeas([]);
  }, [channelId]);

  // Open the script-preview flow. Only available for shorts (the long-video
  // pipeline doesn't expose a single-LLM-call preview yet).
  const startPreview = () => {
    if (!channelId) {
      toast.error("Selecciona un canal");
      return;
    }
    if (kind !== "short") {
      toast.error("La vista previa solo está disponible para shorts");
      return;
    }
    if (imageMode === "upload") {
      toast.error("La vista previa no analiza fotos; inicia el render para usar tus fotos");
      return;
    }
    const url = api.previewScriptUrl(channelId, {
      custom_topic: topic.trim(),
      model: llmProvider && llmModel ? llmModel : undefined,
      llm_provider: llmProvider || undefined,
      llm_reasoning_effort: selectedReasoningEffort,
      llm_mode: selectedLlmMode,
      duration_seconds: shortDuration,
      retention_mode: retentionMode,
    });
    setPreviewSseUrl(url);
    setPreviewOpen(true);
  };

  // When the user approves the preview, kick the full /generate flow but
  // pass `script_file=<previewId>` so the runner reuses the script instead
  // of regenerating it.
  const onPreviewApproved = async (data: { previewId: string }) => {
    if (!channelId) return;
    let photoUploadId = "";
    try {
      photoUploadId = await uploadSelectedPhotos();
    } catch (e) {
      toast.error(`No se pudieron subir las fotos: ${(e as Error).message}`);
      return;
    }
    if (imageMode === "upload" && !photoUploadId) return;

    const serverUploadPlatforms = previewAtEnd ? [] : uploadPlatforms;
    const url = api.generateUrl(channelId, {
      kind: "short",
      custom_topic: topic.trim(),
      image_mode: imageMode === "photos" ? "photos" : "ai",
      image_provider: showImageProviderSelector ? imageProvider : undefined,
      auto_upload: serverUploadPlatforms.length > 0,
      upload_platforms: serverUploadPlatforms,
      series_id: seriesId || undefined,
      duration_seconds: shortDuration,
      render_profile: shortRenderProfile,
      llm_provider: llmProvider || undefined,
      llm_model: llmProvider && llmModel ? llmModel : undefined,
      llm_reasoning_effort: selectedReasoningEffort,
      llm_mode: selectedLlmMode,
      script_file: data.previewId,
      photo_upload_id: photoUploadId || undefined,
      retention_mode: retentionMode,
    });
    setPreviewOpen(false);
    setSseUrl(url);
    setProgressOpen(true);
  };

  const eta = kind === "short"
    ? Math.round(
        shortDuration *
          (shortRenderProfile === "quality"
            ? 0.18
            : shortRenderProfile === "fast"
            ? 0.11
            : 0.07) +
          90 +
          (retentionMode === "maxima_retencion" ? shortDuration * 0.08 + 45 : 0),
      )
    : 900;
  const outputFps = kind === "short" ? SHORT_RENDER_META[shortRenderProfile].fps : 24;

  return (
    <>
      <Header
        eyebrow="· estudio"
        title="Generar contenido"
        description="Pipeline LLM → TTS → imagen → render"
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={startPreview}
              disabled={!channelId || kind !== "short" || imageMode === "upload"}
              title={
                kind !== "short"
                  ? "La vista previa solo está disponible para shorts"
                  : "Revisar el guion antes de renderizar"
              }
            >
              <Eye className="h-4 w-4" />
              <span className="hidden sm:inline">Vista previa</span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => setBatchOpen(true)}
              disabled={channels.length === 0}
              title="Generar varios shorts/largos en paralelo"
            >
              <Layers className="h-4 w-4" />
              <span className="hidden sm:inline">Lote</span>
            </Button>
          </div>
        }
      />

      <PageShell>
        <section className="page-hero">
          <div className="page-hero-inner">
            <div>
              <span className="eyebrow block mb-2">Production board</span>
              <h1 className="page-title">
                Genera el siguiente <span className="brand-text">{kind === "short" ? "short" : "video"}</span>
              </h1>
              <p className="page-subtitle">
                Canal, guion, voz, imagenes y render en una consola unica. El flujo
                queda listo para revisar o subir sin cambiar de pantalla.
              </p>
            </div>
            <div className="metric-strip grid-cols-3 w-full sm:w-auto sm:min-w-[460px]">
              <GenerateMetric label="Canal" value={selectedChannel?.nickname || "sin canal"} colorVar="var(--primary)" />
              <GenerateMetric label="ETA" value={`${eta}s`} colorVar="var(--accent)" />
              <GenerateMetric label="FPS" value={outputFps} colorVar="var(--gold)" />
            </div>
          </div>
        </section>

        <div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_360px] gap-3.5">
          {/* MAIN — 3-stage console */}
          <div
            className="studio-surface overflow-hidden"
            style={{ background: "hsl(var(--card))" }}
          >
            {/* Track headers */}
            <div
              className="grid grid-cols-1 md:grid-cols-3"
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
            <div className="grid grid-cols-1 md:grid-cols-3">
              {/* INPUT */}
              <div
                className="px-[18px] pt-[18px] pb-[22px] flex flex-col gap-3.5 md:border-r"
                style={{ borderColor: "hsl(var(--border) / .07)" }}
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
                  <div className="flex flex-col gap-1.5">
                    <TextArea
                      value={topic}
                      onChange={setTopic}
                      placeholder="Déjalo vacío para que el LLM elija un tema según el niche del canal"
                      rows={3}
                    />
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={fetchTopicIdeas}
                        disabled={!channelId || ideasLoading}
                        className={cn(
                          "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium",
                          "border transition-colors",
                          ideasLoading
                            ? "text-muted-foreground"
                            : "text-foreground hover:bg-surface",
                        )}
                        style={{
                          borderColor: "hsl(var(--border) / .12)",
                          background: "hsl(var(--bg-raised) / .5)",
                        }}
                        title="Pídele al LLM 6 ideas de temas según el niche del canal"
                      >
                        {ideasLoading ? (
                          <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.7} />
                        ) : (
                          <Lightbulb
                            className="h-3 w-3"
                            strokeWidth={1.7}
                            style={{ color: "hsl(var(--gold))" }}
                          />
                        )}
                        {ideasLoading ? "Pensando…" : "Dame ideas"}
                      </button>
                      {topicIdeas.length > 0 && (
                        <button
                          type="button"
                          onClick={() => setTopicIdeas([])}
                          className="inline-flex items-center gap-1 text-[10.5px] text-muted-foreground hover:text-foreground"
                          title="Limpiar ideas sugeridas"
                        >
                          <X className="h-3 w-3" strokeWidth={1.7} />
                          limpiar
                        </button>
                      )}
                    </div>
                    {topicIdeas.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-0.5">
                        {topicIdeas.map((idea) => (
                          <button
                            key={idea}
                            type="button"
                            onClick={() => {
                              setTopic(idea);
                              // Remove the picked idea so the user sees what's
                              // left instead of being tempted to re-click it.
                              setTopicIdeas((prev) => prev.filter((i) => i !== idea));
                            }}
                            className="text-left text-[11.5px] leading-snug px-2.5 py-1.5 rounded-md transition-colors max-w-full"
                            style={{
                              background: "hsl(var(--bg-raised) / .55)",
                              border: "1px solid hsl(var(--border) / .12)",
                              color: "hsl(var(--foreground))",
                            }}
                            title="Usar este tema"
                          >
                            {idea}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
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
                className="px-[18px] pt-[18px] pb-[22px] flex flex-col gap-[18px] md:border-r"
                style={{ borderColor: "hsl(var(--border) / .07)" }}
              >
                {kind === "short" && (
                  <>
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
                    <Field
                      label="Retencion"
                      hint={RETENTION_MODE_META[retentionMode].hint}
                    >
                      <div className="flex items-center gap-2">
                        <Sparkles
                          className="h-4 w-4 shrink-0"
                          strokeWidth={1.7}
                          style={{
                            color:
                              retentionMode === "maxima_retencion"
                                ? "hsl(var(--gold))"
                                : "hsl(var(--muted-foreground))",
                          }}
                        />
                        <Segmented
                          value={retentionMode}
                          onChange={(v) => setRetentionMode(v as RetentionMode)}
                          accentVar="var(--gold)"
                          options={RETENTION_MODE_OPTIONS.map((mode) => ({
                            value: mode,
                            label: RETENTION_MODE_META[mode].label,
                          }))}
                        />
                      </div>
                    </Field>
                    <Field
                      label="Render"
                      hint={SHORT_RENDER_META[shortRenderProfile].hint}
                    >
                      <Segmented
                        value={shortRenderProfile}
                        onChange={(v) => setShortRenderProfile(v as ShortRenderProfile)}
                        accentVar="var(--accent)"
                        options={SHORT_RENDER_PROFILE_OPTIONS.map((p) => ({
                          value: p,
                          label: SHORT_RENDER_META[p].label,
                        }))}
                      />
                    </Field>
                  </>
                )}
                <Field label="Fuente de imágenes">
                  <Segmented
                    value={imageMode}
                    onChange={(v) => {
                      if (!showImageProviderSelector) setImageMode(v as VisualSource);
                    }}
                    accentVar="var(--accent)"
                    disabled={showImageProviderSelector}
                    options={[
                      { value: "ai", label: "AI · Nano Banana" },
                      { value: "photos", label: "Stock fotos" },
                      { value: "upload", label: "Mis fotos" },
                    ]}
                  />
                </Field>

                {showImageProviderSelector && (
                  <Field label="Fotos AI" hint={imageProvider}>
                    <SelectMini
                      value={imageProvider}
                      onChange={(v) => setImageProvider(v as ImageProvider)}
                      options={IMAGE_PROVIDER_OPTIONS}
                      icon={<Sparkles className="h-3 w-3" strokeWidth={1.5} />}
                    />
                  </Field>
                )}

                {imageMode === "upload" && !showImageProviderSelector && (
                  <Field
                    label="Fotos subidas"
                    hint={photoFiles.length ? `${photoFiles.length} archivos` : "jpg/png/webp"}
                  >
                    <div className="flex flex-col gap-2">
                      <input
                        id="photo-video-files"
                        type="file"
                        accept="image/*"
                        multiple
                        className="sr-only"
                        onChange={(event) =>
                          setPhotoFiles(Array.from(event.target.files ?? []))
                        }
                      />
                      <label
                        htmlFor="photo-video-files"
                        className={cn(
                          "inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-lg px-3 text-[12px] font-medium transition-colors",
                          "border text-foreground hover:bg-surface",
                        )}
                        style={{
                          borderColor: "hsl(var(--border) / .13)",
                          background: "hsl(var(--bg-raised) / .55)",
                        }}
                      >
                        <Upload className="h-4 w-4" strokeWidth={1.8} />
                        {photoFiles.length ? "Cambiar fotos" : "Elegir fotos"}
                      </label>
                      {photoFiles.length > 0 && (
                        <div
                          className="max-h-[92px] overflow-auto rounded-lg px-2 py-1.5 text-[11px] leading-relaxed font-mono text-muted-foreground"
                          style={{
                            background: "hsl(var(--background))",
                            border: "1px solid hsl(var(--border) / .07)",
                          }}
                        >
                          {photoFiles.slice(0, 8).map((file) => (
                            <div key={`${file.name}-${file.size}`} className="truncate">
                              {file.name}
                            </div>
                          ))}
                          {photoFiles.length > 8 && (
                            <div>+{photoFiles.length - 8} mas</div>
                          )}
                        </div>
                      )}
                    </div>
                  </Field>
                )}

                <Field
                  label="Hook profile"
                  hint={
                    hookProfile
                      ? "override"
                      : `canal · ${selectedChannel?.hook_profile || "educational"}`
                  }
                >
                  <Segmented
                    value={hookProfile}
                    onChange={(v) => setHookProfile(v as HookProfile | "")}
                    accentVar="var(--accent)"
                    options={[
                      { value: "", label: "Canal" },
                      ...HOOK_PROFILE_OPTIONS.map((p) => ({
                        value: p,
                        label: p,
                      })),
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
                          v === "auto"
                            ? ""
                            : (v as LLMProvider),
                        )
                      }
                      options={[
                        { value: "auto", label: "Auto" },
                        {
                          value: "ollama",
                          label: `Ollama${
                            llmModels.ollama.length ? ` (${llmModels.ollama.length})` : ""
                          }`,
                        },
                        {
                          value: "gemini",
                          label: `Gemini${
                            llmModels.gemini.length ? ` (${llmModels.gemini.length})` : ""
                          }`,
                        },
                        {
                          value: "openai",
                          label: `OpenAI${
                            llmModels.openai.length ? ` (${llmModels.openai.length})` : ""
                          }`,
                        },
                        {
                          value: "claude",
                          label: `Claude${
                            llmModels.claude.length ? ` (${llmModels.claude.length})` : ""
                          }`,
                        },
                        {
                          value: "pollinations",
                          label: `Pollinations${
                            llmModels.pollinations.length
                              ? ` (${llmModels.pollinations.length})`
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
                        options={(llmModels[llmProvider] ?? []).map((m) => ({
                          value: m.id,
                          label: m.label || m.id,
                        }))}
                      />
                    )}
                  </div>
                </Field>
                {llmProvider === "openai" && (
                  <Field label="Thinking" hint={openaiReasoningEffort}>
                    <SelectMini
                      value={openaiReasoningEffort}
                      onChange={(v) => setOpenaiReasoningEffort(v as OpenAIReasoningEffort)}
                      options={OPENAI_REASONING_OPTIONS}
                      icon={<Sparkles className="h-3 w-3" strokeWidth={1.5} />}
                    />
                  </Field>
                )}
                {llmProvider === "claude" && (
                  <div className="grid grid-cols-2 gap-1.5">
                    <Field label="Thinking" hint={claudeReasoningEffort}>
                      <SelectMini
                        value={claudeReasoningEffort}
                        onChange={(v) => setClaudeReasoningEffort(v as ClaudeReasoningEffort)}
                        options={CLAUDE_REASONING_OPTIONS}
                        icon={<Sparkles className="h-3 w-3" strokeWidth={1.5} />}
                      />
                    </Field>
                    <Field label="Modo" hint={claudeMode}>
                      <SelectMini
                        value={claudeMode}
                        onChange={(v) => setClaudeMode(v as LLMRunMode)}
                        options={CLAUDE_MODE_OPTIONS}
                      />
                    </Field>
                  </div>
                )}

                <Field label="Subida" hint={uploadTargetLabel}>
                  <div className="grid grid-cols-3 gap-1.5">
                    <UploadPlatformButton
                      label="Subir a YouTube"
                      active={uploadPlatforms.includes("youtube")}
                      onClick={() => toggleUploadPlatform("youtube")}
                      icon={<Youtube className="h-3.5 w-3.5" strokeWidth={1.8} />}
                    />
                    <UploadPlatformButton
                      label="Subir a TikTok"
                      active={uploadPlatforms.includes("tiktok")}
                      onClick={() => toggleUploadPlatform("tiktok")}
                      icon={<Music2 className="h-3.5 w-3.5" strokeWidth={1.8} />}
                    />
                    <UploadPlatformButton
                      label="Subir a FB"
                      active={uploadPlatforms.includes("facebook")}
                      onClick={() => toggleUploadPlatform("facebook")}
                      icon={<Facebook className="h-3.5 w-3.5" strokeWidth={1.8} />}
                    />
                  </div>
                </Field>
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
                    disabled={!channelId || uploadingPhotos}
                  >
                    {uploadingPhotos ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Play className="h-3.5 w-3.5" />
                    )}
                    {uploadingPhotos ? "Subiendo fotos" : "Imprimir vídeo"}
                  </Button>
                  <div className="mt-2.5 flex items-center justify-between text-[11px] text-muted-foreground font-mono">
                    <span>ETA ~{eta}s</span>
                    <span>
                      · {kind === "short" ? "1080×1920" : "1920×1080"} · {outputFps}fps
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
        uploadPlatforms={uploadPlatforms}
      />

      <ScriptPreviewDialog
        open={previewOpen}
        onOpenChange={(o) => {
          setPreviewOpen(o);
          if (!o) setPreviewSseUrl(null);
        }}
        channelId={channelId}
        kind="short"
        retentionMode={retentionMode}
        sseUrl={previewSseUrl}
        onApprove={onPreviewApproved}
        onRegenerate={startPreview}
      />

      <BatchGenerateDialog
        open={batchOpen}
        onOpenChange={setBatchOpen}
        channels={channels}
        defaults={{
          kind,
          imageMode: imageMode === "photos" ? "photos" : "ai",
          imageProvider: showImageProviderSelector ? imageProvider : undefined,
          autoUpload: uploadPlatforms.includes("youtube"),
          llmProvider: llmProvider || undefined,
          llmReasoningEffort: selectedReasoningEffort,
          llmMode: selectedLlmMode,
          model: llmProvider && llmModel ? llmModel : undefined,
          renderProfile: kind === "short" ? shortRenderProfile : undefined,
          retentionMode: kind === "short" ? retentionMode : undefined,
        }}
      />
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Track header
// ─────────────────────────────────────────────────────────────────────────────
function GenerateMetric({
  label,
  value,
  colorVar,
}: {
  label: string;
  value: string | number;
  colorVar: string;
}) {
  return (
    <div className="px-4 py-3" style={{ borderRight: "1px solid hsl(var(--border) / .06)" }}>
      <div className="flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: `hsl(${colorVar})` }} />
        <span className="tiny-label">{label}</span>
      </div>
      <div className="mt-1 truncate font-mono text-[17px] font-semibold tabular-nums text-foreground">
        {value}
      </div>
    </div>
  );
}

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
      className="px-[18px] py-3.5 relative md:border-r last:border-r-0"
      style={{
        borderColor: rightBorder ? "hsl(var(--border) / .07)" : "transparent",
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
          style={{ letterSpacing: "0", color: `hsl(${colorVar})` }}
        >
          · {num}
        </span>
        <span
          className="font-mono uppercase font-semibold text-[10px]"
          style={{ letterSpacing: "0", color: `hsl(${colorVar})` }}
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
function UploadPlatformButton({
  label,
  active,
  onClick,
  icon,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "h-10 rounded-lg border px-2 text-[11px] font-medium transition-colors",
        "inline-flex items-center justify-center gap-1.5",
        active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
      )}
      style={{
        background: active ? "hsl(var(--primary) / .14)" : "hsl(var(--background))",
        borderColor: active ? "hsl(var(--primary) / .45)" : "hsl(var(--border) / .1)",
      }}
      aria-pressed={active}
      title={label}
    >
      {icon}
      <span className="leading-tight">{label}</span>
    </button>
  );
}

function formatUploadPlatformLabel(platforms: UploadPlatform[]) {
  if (platforms.length === 0) return "solo render";
  const labels: Record<UploadPlatform, string> = {
    youtube: "YouTube",
    tiktok: "TikTok",
    facebook: "FB",
  };
  const selected = platforms.map((platform) => labels[platform]);
  if (selected.length === 1) return selected[0];
  return selected.slice(0, -1).join(", ") + " y " + selected[selected.length - 1];
}

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
      <label className="flex items-center justify-between text-[11px] text-muted-foreground font-medium">
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
  disabled = false,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
  accentVar: string;
  disabled?: boolean;
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
            disabled={disabled}
            onClick={() => onChange(opt.value)}
            className={cn(
              "px-3 py-1.5 rounded-md text-[12px] cursor-pointer",
              disabled && "cursor-not-allowed opacity-50",
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
        <div className="text-[13px] text-foreground font-medium">
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
        style={{ letterSpacing: "0" }}
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
          <div className="text-[13px] font-medium leading-tight truncate">
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
      <h3 className="font-display text-[22px] font-semibold mb-1">
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
        className="font-mono uppercase font-semibold text-[9px]"
        style={{ color: `hsl(${accentVar})` }}
      >
        {label}
      </span>
      <div
        className="font-display text-[18px] font-semibold mt-0.5 truncate"
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
        style={{ letterSpacing: "0" }}
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
