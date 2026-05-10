import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Sparkles,
  Image as ImageIcon,
  Camera,
  Wand2,
  UploadCloud,
  Youtube,
  BookOpen,
  Hash,
  Clapperboard,
  Timer,
  Eye,
} from 'lucide-react';
import { Header } from '@/components/layout/Header';
import { PageShell } from '@/components/layout/AppShell';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { ProgressDialog } from '@/components/ProgressDialog';
import {
  api,
  SHORT_DURATION_OPTIONS,
  type Channel,
  type SeriesEntry,
  type ShortDurationSeconds,
} from '@/lib/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

export function Generate() {
  const [params] = useSearchParams();
  const presetChannel = params.get('channel') || '';

  const [channels, setChannels] = useState<Channel[]>([]);
  const [series, setSeries] = useState<SeriesEntry[]>([]);
  const [channelId, setChannelId] = useState(presetChannel);
  const [kind, setKind] = useState<'short' | 'long'>('short');
  const [topic, setTopic] = useState('');
  const [imageMode, setImageMode] = useState<'ai' | 'photos'>('ai');
  const [seriesId, setSeriesId] = useState('');
  const [autoUpload, setAutoUpload] = useState(false);
  const [previewAtEnd, setPreviewAtEnd] = useState(false);
  const [shortDuration, setShortDuration] = useState<ShortDurationSeconds>(60);

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
    api
      .listSeries()
      .then(setSeries)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedChannel = useMemo(
    () => channels.find((c) => c.id === channelId),
    [channels, channelId],
  );

  const start = () => {
    if (!channelId) {
      toast.error('Selecciona un canal');
      return;
    }
    // When previewAtEnd is on, the upload must wait until the user closes the
    // preview modal. We render-only on the backend and trigger upload-last
    // from the frontend after the preview closes.
    const serverAutoUpload = autoUpload && !previewAtEnd;
    const url = api.generateUrl(channelId, {
      kind,
      custom_topic: topic.trim(),
      image_mode: imageMode,
      auto_upload: serverAutoUpload,
      series_id: seriesId || undefined,
      duration_seconds: kind === 'short' ? shortDuration : undefined,
    });
    setSseUrl(url);
    setProgressOpen(true);
  };

  return (
    <>
      <Header
        title="Generar contenido"
        description="Crea un short o video largo desde aquí. Verás el progreso en vivo."
      />

      <PageShell>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Wand2 className="h-5 w-5 text-primary" />
                  Configuración del job
                </CardTitle>
                <CardDescription>
                  Elige canal, formato y opciones. Después dale a "Iniciar
                  generación".
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Channel selector */}
                <div className="space-y-2">
                  <Label>Canal</Label>
                  <Select value={channelId} onValueChange={setChannelId}>
                    <SelectTrigger>
                      <SelectValue placeholder="Selecciona un canal" />
                    </SelectTrigger>
                    <SelectContent>
                      {channels.length === 0 && (
                        <div className="px-3 py-2 text-sm text-muted-foreground">
                          No hay canales — crea uno primero
                        </div>
                      )}
                      {channels.map((c) => (
                        <SelectItem key={c.id} value={c.id}>
                          {c.nickname}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Kind tabs */}
                <div className="space-y-2">
                  <Label>Tipo de contenido</Label>
                  <Tabs
                    value={kind}
                    onValueChange={(v) => setKind(v as 'short' | 'long')}
                  >
                    <TabsList className="grid grid-cols-2 w-full max-w-md">
                      <TabsTrigger value="short" className="gap-2">
                        <Sparkles className="h-3.5 w-3.5" /> Short
                      </TabsTrigger>
                      <TabsTrigger value="long" className="gap-2">
                        <Clapperboard className="h-3.5 w-3.5" /> Long video
                      </TabsTrigger>
                    </TabsList>
                    <TabsContent
                      value="short"
                      className="text-xs text-muted-foreground"
                    >
                      Video vertical 9:16, 30–60s. Pipeline rápido (~2–4 min).
                    </TabsContent>
                    <TabsContent
                      value="long"
                      className="text-xs text-muted-foreground"
                    >
                      Video largo 5–20 min con narración extendida. Toma ~15–25
                      min.
                    </TabsContent>
                  </Tabs>
                </div>

                {/* Topic */}
                <div className="space-y-2">
                  <Label htmlFor="topic">
                    Tema personalizado{' '}
                    <span className="text-muted-foreground">(opcional)</span>
                  </Label>
                  <Textarea
                    id="topic"
                    rows={2}
                    value={topic}
                    onChange={(e) => setTopic(e.target.value)}
                    placeholder="Déjalo vacío para que el LLM elija un tema según el niche del canal"
                  />
                </div>

                {/* Duration preset (only for shorts) */}
                {kind === 'short' && (
                  <div className="space-y-2">
                    <Label className="flex items-center gap-1.5">
                      <Timer className="h-4 w-4" /> Duración del short
                    </Label>
                    <div className="grid grid-cols-3 gap-3">
                      {SHORT_DURATION_OPTIONS.map((opt) => (
                        <DurationCard
                          key={opt}
                          active={shortDuration === opt}
                          onClick={() => setShortDuration(opt)}
                          minutes={opt / 60}
                          seconds={opt}
                          description={
                            opt === 60
                              ? '~150 palabras · 12 frases · 6 imgs'
                              : opt === 120
                                ? '~310 palabras · 22 frases · 10 imgs'
                                : '~470 palabras · 32 frases · 14 imgs'
                          }
                        />
                      ))}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Calibrado para narración en español a ~150 wpm. El render
                      cae sobre la marca, nunca por debajo.
                    </p>
                  </div>
                )}

                {/* Image mode (only for shorts) */}
                {kind === 'short' && (
                  <div className="space-y-2">
                    <Label>Fuente de imágenes</Label>
                    <div className="grid grid-cols-2 gap-3">
                      <ModeCard
                        active={imageMode === 'ai'}
                        onClick={() => setImageMode('ai')}
                        icon={ImageIcon}
                        title="AI generado"
                        description="Leonardo AI / fallback. Más control de estética."
                      />
                      <ModeCard
                        active={imageMode === 'photos'}
                        onClick={() => setImageMode('photos')}
                        icon={Camera}
                        title="Fotos stock"
                        description="Busca fotos reales en Wikipedia y museos. Si no las encuentra, prueba bancos de stock y, como último recurso, genera con AI."
                      />
                    </div>
                  </div>
                )}

                {/* Series (only for long) */}
                {kind === 'long' && series.length > 0 && (
                  <div className="space-y-2">
                    <Label>Serie</Label>
                    <Select
                      value={seriesId || '__none__'}
                      onValueChange={(v) =>
                        setSeriesId(v === '__none__' ? '' : v)
                      }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="(ninguna)" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">(ninguna)</SelectItem>
                        {series.map((s) => (
                          <SelectItem key={s.id} value={s.id}>
                            {s.name || s.id}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      Aplica template y prompt brief de la serie elegida.
                    </p>
                  </div>
                )}

                {/* Auto upload */}
                <div className="flex items-center justify-between rounded-lg border border-border p-3">
                  <div className="space-y-0.5">
                    <Label className="flex items-center gap-1.5">
                      <UploadCloud className="h-4 w-4" /> Subir automáticamente
                      al terminar
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      Lanza Selenium con el perfil Firefox del canal cuando el
                      render termine.
                    </p>
                  </div>
                  <Switch
                    checked={autoUpload}
                    onCheckedChange={setAutoUpload}
                  />
                </div>

                {/* Preview at end */}
                <div className="flex items-center justify-between rounded-lg border border-border p-3">
                  <div className="space-y-0.5">
                    <Label className="flex items-center gap-1.5">
                      <Eye className="h-4 w-4" /> Hacer preview al terminar
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      {autoUpload
                        ? 'Abre el video en un modal cuando termine el render. Al cerrarlo, arranca la subida.'
                        : 'Abre el video en un modal cuando termine el render para revisarlo.'}
                    </p>
                  </div>
                  <Switch
                    checked={previewAtEnd}
                    onCheckedChange={setPreviewAtEnd}
                  />
                </div>

                <div className="flex items-center gap-3 pt-2">
                  <Button
                    variant="brand"
                    size="lg"
                    onClick={start}
                    disabled={!channelId}
                    className="gap-2"
                  >
                    <Sparkles className="h-4 w-4" /> Iniciar generación
                  </Button>
                  <span className="text-xs text-muted-foreground">
                    Verás el progreso en vivo igual que el terminal.
                  </span>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Side panel: channel summary */}
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Youtube className="h-4 w-4 text-primary" /> Canal
                  seleccionado
                </CardTitle>
              </CardHeader>
              <CardContent>
                {selectedChannel ? (
                  <div className="space-y-3 text-sm">
                    <div>
                      <div className="font-semibold">
                        {selectedChannel.nickname}
                      </div>
                      <div className="text-xs text-muted-foreground line-clamp-2">
                        {selectedChannel.niche || '(sin niche)'}
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <Mini
                        label="Idioma"
                        value={selectedChannel.language || 'es'}
                      />
                      <Mini
                        label="Videos"
                        value={String(selectedChannel.videos_count)}
                      />
                      <Mini
                        label="Voz short"
                        value={selectedChannel.short_voice || 'default'}
                      />
                      <Mini
                        label="Voz long"
                        value={selectedChannel.long_voice || 'default'}
                      />
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Selecciona un canal para ver detalles.
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <BookOpen className="h-4 w-4 text-accent" /> Tips
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs text-muted-foreground">
                <Tip>
                  Si el canal tiene un image_style configurado, se aplica a cada
                  prompt automáticamente.
                </Tip>
                <Tip>
                  Para shorts en serie sobre un mismo personaje, escribe el
                  nombre exacto en el tema.
                </Tip>
                <Tip>
                  El modo "fotos stock" busca primero en archivos curados
                  (Wikipedia, Wikimedia, Europeana, el Met, la Library of
                  Congress). Si nada encaja, prueba con bancos de stock
                  (Pexels, Pixabay) y al final cae a AI. Ideal para historia
                  y temas con archivo real.
                </Tip>
                <Tip>
                  La subida usa Selenium contra YouTube Studio. El perfil
                  Firefox debe estar pre-loggeado.
                </Tip>
              </CardContent>
            </Card>

            {selectedChannel && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Hash className="h-4 w-4 text-gold" /> Estilo
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-xs font-mono whitespace-pre-wrap text-muted-foreground bg-muted/40 rounded-md p-3 max-h-40 overflow-auto scrollbar-thin">
                    {selectedChannel.image_style ||
                      '(default — no se inyecta estilo)'}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </PageShell>

      <ProgressDialog
        open={progressOpen}
        onOpenChange={setProgressOpen}
        title={kind === 'short' ? 'Generando short' : 'Generando video largo'}
        description={
          autoUpload && previewAtEnd
            ? 'Render → preview al terminar → subida al cerrar el preview.'
            : autoUpload
              ? 'Render + upload automático al terminar.'
              : previewAtEnd
                ? 'Render → preview al terminar para que lo revises.'
                : 'Solo render — al terminar puedes revisar y subir desde aquí.'
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

function ModeCard({
  active,
  onClick,
  icon: Icon,
  title,
  description,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof ImageIcon;
  title: string;
  description: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'text-left rounded-lg border p-3 transition-all',
        active
          ? 'border-primary bg-primary/5 shadow-sm'
          : 'border-border hover:border-border/80 hover:bg-muted/30',
      )}
    >
      <div className="flex items-center gap-2">
        <div
          className={cn(
            'rounded-md p-1.5',
            active
              ? 'bg-primary/15 text-primary'
              : 'bg-muted text-muted-foreground',
          )}
        >
          <Icon className="h-4 w-4" />
        </div>
        <span className="font-medium text-sm">{title}</span>
        {active && <Badge className="ml-auto">activo</Badge>}
      </div>
      <p className="text-xs text-muted-foreground mt-2">{description}</p>
    </button>
  );
}

function DurationCard({
  active,
  onClick,
  minutes,
  seconds,
  description,
}: {
  active: boolean;
  onClick: () => void;
  minutes: number;
  seconds: number;
  description: string;
}) {
  const label = Number.isInteger(minutes) ? `${minutes} min` : `${seconds}s`;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'text-left rounded-lg border p-3 transition-all',
        active
          ? 'border-primary bg-primary/5 shadow-sm'
          : 'border-border hover:border-border/80 hover:bg-muted/30',
      )}
    >
      <div className="flex items-baseline gap-1.5">
        <span className="text-lg font-semibold">{label}</span>
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
          ({seconds}s)
        </span>
        {active && <Badge className="ml-auto">activo</Badge>}
      </div>
      <p className="text-xs text-muted-foreground mt-1.5">{description}</p>
    </button>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-muted/50 px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="text-xs font-medium truncate">{value}</div>
    </div>
  );
}

function Tip({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-1.5 h-1 w-1 rounded-full bg-accent shrink-0" />
      <span>{children}</span>
    </div>
  );
}
