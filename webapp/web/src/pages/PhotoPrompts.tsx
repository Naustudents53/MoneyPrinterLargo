import { useEffect, useMemo, useState } from "react";
import {
  Copy,
  Download,
  ImagePlus,
  Loader2,
  RefreshCw,
  Sparkles,
  Wand2,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  api,
  RETENTION_MODE_OPTIONS,
  type Channel,
  type LLMModel,
  type PhotoPromptOption,
  type PhotoPromptResponse,
  type RetentionMode,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const DEFAULT_RATIOS: PhotoPromptOption[] = [
  { id: "9:16", label: "9:16", description: "vertical short / reels" },
  { id: "16:9", label: "16:9", description: "wide YouTube thumbnail or cinematic frame" },
  { id: "1:1", label: "1:1", description: "square social image" },
  { id: "4:5", label: "4:5", description: "portrait feed image" },
  { id: "3:2", label: "3:2", description: "classic photo frame" },
];

type ProviderValue = "auto" | "gemini" | "ollama" | "openai" | "pollinations";

export function PhotoPrompts() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [channelId, setChannelId] = useState("");
  const [topic, setTopic] = useState("");
  const [count, setCount] = useState("6");
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [language, setLanguage] = useState("espanol");
  const [retentionMode, setRetentionMode] = useState<RetentionMode>("maxima_retencion");
  const [provider, setProvider] = useState<ProviderValue>("auto");
  const [model, setModel] = useState("");
  const [ratios, setRatios] = useState<PhotoPromptOption[]>(DEFAULT_RATIOS);
  const [models, setModels] = useState<LLMModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PhotoPromptResponse | null>(null);
  const [resultOpen, setResultOpen] = useState(false);

  useEffect(() => {
    api.photoPromptOptions()
      .then((data) => {
        if (data.aspect_ratios?.length) setRatios(data.aspect_ratios);
      })
      .catch(() => {});
    api.listChannels()
      .then((data) => {
        setChannels(data);
        if (!channelId && data.length > 0) setChannelId(data[0].id);
      })
      .catch(() => {});
    api.listLLMModels()
      .then((data) => setModels(data.models ?? []))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedChannel = useMemo(
    () => channels.find((item) => item.id === channelId) || channels[0],
    [channels, channelId],
  );
  const selectedRatio = useMemo(
    () => ratios.find((item) => item.id === aspectRatio) || ratios[0],
    [aspectRatio, ratios],
  );
  const providerModels = useMemo(
    () => provider === "auto" ? [] : models.filter((item) => item.provider === provider),
    [models, provider],
  );

  useEffect(() => {
    if (provider === "auto") {
      setModel("");
      return;
    }
    if (!providerModels.some((item) => item.id === model)) {
      setModel(providerModels[0]?.id || "");
    }
  }, [provider, providerModels, model]);

  useEffect(() => {
    if (selectedChannel?.language) setLanguage(selectedChannel.language);
  }, [selectedChannel?.language]);

  const generate = async () => {
    if (loading) return;
    setLoading(true);
    try {
      const data = await api.generatePhotoPrompts({
        channel_id: channelId,
        topic: topic.trim(),
        count: Number(count),
        style: "project_channel",
        aspect_ratio: aspectRatio,
        language,
        llm_provider: provider === "auto" ? "" : provider,
        llm_model: provider === "auto" ? "" : model,
        retention_mode: retentionMode,
      });
      setResult(data);
      setResultOpen(true);
      if (data.generated_topic) {
        setTopic(data.topic);
        toast.success("Tema generado por el LLM");
      } else {
        toast.success("Prompts listos");
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const copyResult = async () => {
    if (!result?.text) return;
    try {
      await navigator.clipboard.writeText(result.text);
      toast.success("Texto copiado");
    } catch (e) {
      toast.error(`No se pudo copiar: ${(e as Error).message}`);
    }
  };

  const downloadResult = () => {
    if (!result?.text) return;
    const blob = new Blob([result.text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = result.filename || `prompts_fotos_${slugify(result.topic)}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <Header
        eyebrow="Image lab"
        title="Prompts para fotos"
        description="Prompts alineados al canal y al metodo real de imagenes del proyecto."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={generate}
            disabled={loading}
            className="gap-2"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
            Generar
          </Button>
        }
      />

      <PageShell>
        <section className="page-hero">
          <div className="page-hero-inner">
            <div>
              <span className="eyebrow block mb-2">Prompt lab</span>
              <h1 className="page-title">
                Fotos con <span className="brand-text">direccion visual</span>
              </h1>
              <p className="page-subtitle">
                Selecciona el canal, escribe un tema o deja que el LLM lo proponga.
                El pack sale desde un guion base y las mismas reglas visuales del render.
              </p>
            </div>
            <div className="metric-strip grid-cols-3 w-full sm:w-auto sm:min-w-[460px]">
              <PromptMetric label="Prompts" value={count} tone="primary" />
              <PromptMetric label="Canal" value={selectedChannel?.nickname || "auto"} tone="accent" />
              <PromptMetric label="Tema" value={topic.trim() ? "manual" : "LLM"} tone="gold" />
            </div>
          </div>
        </section>

        <div className="grid grid-cols-1 xl:grid-cols-[420px_minmax(0,1fr)] gap-5">
          <Card className="self-start overflow-hidden">
            <span
              aria-hidden
              className="block h-[3px] w-full"
              style={{
                background: "linear-gradient(90deg, hsl(var(--primary)), hsl(var(--accent)), hsl(var(--gold)))",
              }}
            />
            <CardHeader className="pb-4">
              <span className="eyebrow flex items-center gap-1.5">
                <Sparkles className="h-3 w-3" /> Generador
              </span>
              <CardTitle className="text-lg mt-1">Prompt pack</CardTitle>
              <CardDescription className="text-[12px]">
                Usa canal, niche, image_style, guion base y prompt por seccion.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <FieldSelect
                label="Canal"
                value={channelId || selectedChannel?.id || ""}
                onValueChange={setChannelId}
                items={channels.map((channel) => ({
                  id: channel.id,
                  label: channel.nickname || channel.id,
                  description: channel.niche || "sin niche",
                }))}
              />

              <div className="space-y-2">
                <Label htmlFor="photo-topic" className="text-[11px] uppercase font-mono text-muted-foreground">
                  Tema base
                </Label>
                <Textarea
                  id="photo-topic"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  rows={4}
                  placeholder="Ej: TON 618: el agujero negro mas grande conocido, o dejalo vacio"
                  className="resize-none"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <FieldSelect
                  label="Cantidad"
                  value={count}
                  onValueChange={setCount}
                  items={["4", "6", "8", "10", "12"].map((value) => ({
                    id: value,
                    label: value,
                    description: "prompts",
                  }))}
                />
                <FieldSelect
                  label="Formato"
                  value={aspectRatio}
                  onValueChange={setAspectRatio}
                  items={ratios}
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <FieldSelect
                  label="Idioma"
                  value={language}
                  onValueChange={setLanguage}
                  items={[
                    { id: "espanol", label: "Espanol", description: "etiquetas en espanol" },
                    { id: "english", label: "English", description: "English labels" },
                  ]}
                />
                <FieldSelect
                  label="Retencion"
                  value={retentionMode}
                  onValueChange={(value) => {
                    if (RETENTION_MODE_OPTIONS.includes(value as RetentionMode)) {
                      setRetentionMode(value as RetentionMode);
                    }
                  }}
                  items={[
                    { id: "maxima_retencion", label: "MAXIMA RETENCION", description: "beat map + primer frame fuerte" },
                    { id: "standard", label: "Estandar", description: "flujo normal del proyecto" },
                  ]}
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <FieldSelect
                  label="LLM"
                  value={provider}
                  onValueChange={(value) => setProvider(value as ProviderValue)}
                  items={[
                    { id: "auto", label: "Auto", description: "config actual" },
                    { id: "gemini", label: "Gemini", description: "Google" },
                    { id: "ollama", label: "Ollama", description: "local/cloud" },
                    { id: "openai", label: "OpenAI", description: "API" },
                    { id: "pollinations", label: "Pollinations", description: "gratis" },
                  ]}
                />
              </div>

              {provider !== "auto" && (
                <div className="space-y-2">
                  <Label className="text-[11px] uppercase font-mono text-muted-foreground">
                    Modelo
                  </Label>
                  <Select value={model || "none"} onValueChange={(value) => setModel(value === "none" ? "" : value)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Modelo" />
                    </SelectTrigger>
                    <SelectContent>
                      {providerModels.length === 0 ? (
                        <SelectItem value="none">Default del proveedor</SelectItem>
                      ) : (
                        providerModels.map((item) => (
                          <SelectItem key={item.id} value={item.id}>
                            {item.label}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                </div>
              )}

              <Button
                variant="brand"
                size="lg"
                onClick={generate}
                disabled={loading}
                className="w-full gap-2"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
                Crear prompts
              </Button>
            </CardContent>
          </Card>

          <div className="space-y-4">
            <div className="studio-surface p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <span className="eyebrow block mb-2">Salida</span>
                  <h2 className="font-display text-2xl font-semibold">Pack copiable en modal</h2>
                  <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
                    Cada bloque nace de una seccion del guion base. El positive prompt
                    ya viene con el estilo del canal aplicado como en el render.
                  </p>
                </div>
                {result && (
                  <Button variant="outline" onClick={() => setResultOpen(true)} className="gap-2">
                    <RefreshCw className="h-4 w-4" />
                    Reabrir modal
                  </Button>
                )}
              </div>

              <div className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-3">
                <PreviewTile
                  title={selectedChannel?.nickname || "Canal"}
                  text={selectedChannel?.niche || "Selecciona un canal para heredar niche e image_style."}
                  tone="primary"
                />
                <PreviewTile
                  title={selectedRatio?.label || "9:16"}
                  text={selectedRatio?.description || ""}
                  tone="accent"
                />
                <PreviewTile
                  title="Proyecto"
                  text="Tema, guion base, prompt por seccion, estilo del canal y negative prompt."
                  tone="gold"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <ExampleBlock
                title="Positive prompt"
                lines={[
                  "Project scene prompt + image_style del canal",
                  "seccion literal del guion, no galeria random",
                  "context profile: setting, anchors, must avoid",
                  "aspect ratio y no texto dentro de la imagen",
                ]}
              />
              <ExampleBlock
                title="Negative prompt"
                lines={[
                  "generic stock image and wrong subject",
                  "random scientist at monitor / random observatory",
                  "collage, montage, storyboard, split screen",
                  "watermark, captions, logo, bad anatomy",
                ]}
              />
            </div>
          </div>
        </div>
      </PageShell>

      <Dialog open={resultOpen} onOpenChange={setResultOpen}>
        <DialogContent className="max-w-5xl max-h-[90vh] grid-rows-[auto_minmax(0,1fr)_auto]">
          <DialogHeader>
            <div className="flex flex-wrap items-center gap-2 pr-8">
              <DialogTitle>Prompts para fotos</DialogTitle>
              {result?.generated_topic && <Badge variant="gold">tema LLM</Badge>}
              {result && <Badge variant="outline">{result.count} prompts</Badge>}
              {result && <Badge variant="outline">{result.aspect_ratio}</Badge>}
              {result?.channel_nickname && <Badge variant="outline">{result.channel_nickname}</Badge>}
            </div>
            <DialogDescription className="break-words">
              {result?.topic || "Resultado generado"}
            </DialogDescription>
          </DialogHeader>

          <Textarea
            readOnly
            value={result?.text || ""}
            className="min-h-[52vh] resize-none font-mono text-xs leading-relaxed"
          />

          <DialogFooter className="gap-2 flex-wrap">
            <Button variant="outline" onClick={copyResult} disabled={!result} className="gap-2">
              <Copy className="h-4 w-4" />
              Copiar texto
            </Button>
            <Button variant="outline" onClick={downloadResult} disabled={!result} className="gap-2">
              <Download className="h-4 w-4" />
              Descargar .txt
            </Button>
            <Button onClick={() => setResultOpen(false)}>Cerrar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function FieldSelect({
  label,
  value,
  onValueChange,
  items,
}: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  items: PhotoPromptOption[];
}) {
  return (
    <div className="space-y-2">
      <Label className="text-[11px] uppercase font-mono text-muted-foreground">
        {label}
      </Label>
      <Select value={value} onValueChange={onValueChange}>
        <SelectTrigger>
          <SelectValue placeholder={label} />
        </SelectTrigger>
        <SelectContent>
          {items.map((item) => (
            <SelectItem key={item.id} value={item.id}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {items.find((item) => item.id === value)?.description && (
        <p className="text-[11px] text-muted-foreground">
          {items.find((item) => item.id === value)?.description}
        </p>
      )}
    </div>
  );
}

function PromptMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "primary" | "accent" | "gold";
}) {
  const color = tone === "primary" ? "var(--primary)" : tone === "accent" ? "var(--accent)" : "var(--gold)";
  return (
    <div className="px-4 py-3" style={{ borderLeft: "1px solid hsl(var(--border) / .06)" }}>
      <span className="tiny-label">{label}</span>
      <div className="mt-1 truncate font-mono text-[17px] font-semibold" style={{ color: `hsl(${color})` }}>
        {value}
      </div>
    </div>
  );
}

function PreviewTile({
  title,
  text,
  tone,
}: {
  title: string;
  text: string;
  tone: "primary" | "accent" | "gold";
}) {
  const color = tone === "primary" ? "text-primary" : tone === "accent" ? "text-accent" : "text-gold";
  return (
    <div className="soft-panel p-4">
      <div className={cn("font-mono text-xs font-semibold uppercase", color)}>
        {title}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{text}</p>
    </div>
  );
}

function ExampleBlock({ title, lines }: { title: string; lines: string[] }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {lines.map((line) => (
            <div
              key={line}
              className="rounded-lg border border-border/10 bg-background/40 px-3 py-2 text-xs text-muted-foreground"
            >
              {line}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function slugify(value: string) {
  return (value || "tema-generado")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 70) || "tema-generado";
}
