import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Trash2,
  ExternalLink,
  Pencil,
  Sparkles,
  UploadCloud,
  Eraser,
  Search,
  Film,
  Calendar,
  Clapperboard,
  RefreshCw,
  Eye,
  ThumbsUp,
  ThumbsDown,
  MessageSquare,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api, type Channel, type ChannelVideo } from "@/lib/api";
import { ChannelFormDialog } from "./ChannelFormDialog";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ProgressDialog } from "@/components/ProgressDialog";
import { toast } from "sonner";
import { formatDate, relativeTime, truncate, formatCount, formatCompact } from "@/lib/utils";

export function ChannelDetail() {
  const { id } = useParams<{ id: string }>();
  const [channel, setChannel] = useState<Channel | null>(null);
  const [videos, setVideos] = useState<ChannelVideo[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState<"all" | "short" | "long">("all");
  const [editing, setEditing] = useState(false);
  const [deletingVideo, setDeletingVideo] = useState<ChannelVideo | null>(null);
  const [editingVideo, setEditingVideo] = useState<ChannelVideo | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editSubject, setEditSubject] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editIsShort, setEditIsShort] = useState(false);
  const [savingVideo, setSavingVideo] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const openEditVideo = (v: ChannelVideo) => {
    setEditingVideo(v);
    setEditTitle(v.title || "");
    setEditSubject(v.subject || "");
    setEditDescription(v.description || "");
    setEditIsShort(v.is_short);
  };

  const saveVideoEdits = async () => {
    if (!id || !editingVideo) return;
    setSavingVideo(true);
    try {
      await api.editVideo(id, {
        url: editingVideo.url,
        date: editingVideo.date,
        title: editTitle,
        subject: editSubject,
        description: editDescription,
        is_short: editIsShort,
      });
      toast.success("Video actualizado");
      setEditingVideo(null);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSavingVideo(false);
    }
  };

  const markAllAs = async (kind: "short" | "long") => {
    if (!id) return;
    try {
      const r = await api.markAllVideosKind(id, kind);
      toast.success(`${r.updated} marcado(s) como ${kind === "short" ? "Short" : "Long"}`);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [c, v] = await Promise.all([api.getChannel(id), api.listVideos(id)]);
      setChannel(c);
      setVideos(v);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const filtered = videos.filter((v) => {
    if (kindFilter === "short" && !v.is_short) return false;
    if (kindFilter === "long" && v.is_short) return false;
    if (
      search &&
      !v.title.toLowerCase().includes(search.toLowerCase()) &&
      !v.subject.toLowerCase().includes(search.toLowerCase())
    )
      return false;
    return true;
  });

  const shortCount = videos.filter((v) => v.is_short).length;
  const longCount = videos.length - shortCount;

  const handleDeleteVideo = async () => {
    if (!id || !deletingVideo) return;
    try {
      await api.deleteVideo(id, { url: deletingVideo.url, date: deletingVideo.date });
      toast.success("Video eliminado del historial");
      setDeletingVideo(null);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const handleClear = async () => {
    if (!id) return;
    try {
      await api.clearVideos(id);
      toast.success("Historial limpio");
      setClearing(false);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <>
      <Header
        title={channel?.nickname ?? "Canal"}
        description={channel?.niche || "—"}
        actions={
          <div className="flex items-center gap-2">
            <Button asChild variant="brand" size="sm" className="gap-2">
              <Link to={`/generate?channel=${id}`}>
                <Sparkles className="h-4 w-4" /> Generar
              </Link>
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={() => setUploadOpen(true)}
            >
              <UploadCloud className="h-4 w-4" /> Subir último
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={() => setSyncing(true)}
              title="Sincroniza este canal con YouTube"
            >
              <RefreshCw className="h-4 w-4" /> Sync YT
            </Button>
            <Button variant="ghost" size="icon" onClick={() => setEditing(true)}>
              <Pencil className="h-4 w-4" />
            </Button>
          </div>
        }
      />

      <PageShell>
        <Button asChild variant="ghost" size="sm" className="gap-1.5 -ml-2">
          <Link to="/channels">
            <ArrowLeft className="h-4 w-4" /> Volver a canales
          </Link>
        </Button>

        {/* Channel summary — editorial telemetry strip */}
        {channel && !loading ? (
          <div className="studio-surface overflow-hidden">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7">
              <SummaryItem
                label="Suscriptores"
                value={
                  channel.subscriber_count == null
                    ? "—"
                    : formatCompact(channel.subscriber_count)
                }
                hint={
                  channel.subscriber_count == null
                    ? "Sin sincronizar — corre Sync YT"
                    : channel.stats_synced_at
                    ? `Sync: ${channel.stats_synced_at}`
                    : undefined
                }
                fullValue={
                  channel.subscriber_count != null
                    ? channel.subscriber_count.toLocaleString("es-ES")
                    : undefined
                }
                highlight={channel.subscriber_count != null}
                dotVar="var(--violeta)"
              />
              <SummaryItem
                label="Videos"
                value={`${channel.videos_count}`}
                dotVar="var(--primary)"
              />
              <SummaryItem
                label="Idioma"
                value={channel.language || "—"}
                dotVar="var(--accent)"
              />
              <SummaryItem
                label="Voz short"
                value={channel.short_voice || "default"}
                dotVar="var(--gold)"
              />
              <SummaryItem
                label="Voz long"
                value={channel.long_voice || "default"}
                dotVar="var(--lima)"
              />
              <SummaryItem
                label="Estilo"
                value={truncate(channel.image_style, 24) || "default"}
                dotVar="var(--violeta)"
              />
              <SummaryItem
                label="Hook profile"
                value={channel.hook_profile || "default"}
                dotVar="var(--success)"
                last
              />
            </div>
          </div>
        ) : (
          <Skeleton className="h-[80px]" />
        )}

        <div className="studio-surface overflow-hidden">
          {/* Header / toolbar */}
          <div className="px-5 pt-[18px] pb-4 flex items-end justify-between gap-4 flex-wrap">
            <div>
              <span className="eyebrow text-muted-foreground">· historial</span>
              <h2 className="font-display text-[20px] font-semibold tracking-tight text-foreground mt-1">
                Historial de videos
              </h2>
              <p className="text-[12px] text-muted-foreground mt-0.5">
                Lista de videos generados y registrados en el caché.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <div
                className="inline-flex rounded-lg p-0.5"
                style={{
                  background: "hsl(var(--bg-raised) / .6)",
                  border: "1px solid hsl(var(--border) / .07)",
                }}
              >
                <KindTab
                  active={kindFilter === "all"}
                  onClick={() => setKindFilter("all")}
                  label="Todos"
                  count={videos.length}
                />
                <KindTab
                  active={kindFilter === "short"}
                  onClick={() => setKindFilter("short")}
                  icon={Sparkles}
                  label="Shorts"
                  count={shortCount}
                />
                <KindTab
                  active={kindFilter === "long"}
                  onClick={() => setKindFilter("long")}
                  icon={Clapperboard}
                  label="Largos"
                  count={longCount}
                />
              </div>
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Buscar por título o tema…"
                  className="pl-8 h-9 w-72"
                />
              </div>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-2"
                    disabled={videos.length === 0}
                  >
                    <Pencil className="h-4 w-4" /> Marcar tipo…
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuLabel>Aplicar a TODOS los videos</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => markAllAs("short")} className="gap-2">
                    <Sparkles className="h-3.5 w-3.5" /> Marcar todos como Short
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => markAllAs("long")} className="gap-2">
                    <Clapperboard className="h-3.5 w-3.5" /> Marcar todos como Long
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setClearing(true)}
                className="gap-2 text-destructive hover:text-destructive"
                disabled={videos.length === 0}
              >
                <Eraser className="h-4 w-4" /> Limpiar todo
              </Button>
            </div>
          </div>

          {loading ? (
            <div className="px-5 pb-5 space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-16" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="px-5 pb-5">
              <EmptyState
                icon={Film}
                title={search ? "Sin coincidencias" : "Sin videos en el historial"}
                description={
                  search
                    ? "Prueba otro término de búsqueda."
                    : "Genera un short o video largo desde la página de generación."
                }
                action={
                  !search ? (
                    <Button asChild variant="brand">
                      <Link to={`/generate?channel=${id}`}>Generar el primero</Link>
                    </Button>
                  ) : undefined
                }
              />
            </div>
          ) : (
            <>
              {/* Column headers — eyebrow style */}
              <div
                className="hidden lg:grid items-center gap-4 px-5 py-2 text-[10px] font-mono uppercase font-semibold text-muted-foreground"
                style={{
                  letterSpacing: "0.18em",
                  gridTemplateColumns: "72px minmax(0,2.2fr) minmax(0,1.4fr) 130px minmax(0,1fr) 100px",
                  borderTop: "1px solid hsl(var(--border) / .04)",
                  background: "hsl(var(--bg-raised) / .4)",
                }}
              >
                <span>Tipo</span>
                <span>Título</span>
                <span className="hidden xl:block">Subject</span>
                <span>Fecha</span>
                <span className="hidden xl:block">Engagement</span>
                <span className="text-right">Acciones</span>
              </div>

              {/* Rows */}
              <div>
                {filtered.map((v) => (
                  <VideoRow
                    key={v.index}
                    video={v}
                    onOpen={() => openEditVideo(v)}
                    onDelete={() => setDeletingVideo(v)}
                  />
                ))}
              </div>

              <div
                className="px-5 py-2.5 text-[11px] font-mono text-muted-foreground flex items-center gap-2 flex-wrap"
                style={{
                  borderTop: "1px solid hsl(var(--border) / .07)",
                  background: "hsl(var(--bg-raised) / .4)",
                }}
              >
                <span>
                  Mostrando{" "}
                  <span className="text-foreground tabular-nums">{filtered.length}</span>{" "}
                  de{" "}
                  <span className="text-foreground tabular-nums">{videos.length}</span>{" "}
                  videos
                </span>
                {videos.some((v) => !v.url || !v.url.startsWith("http")) && (
                  <Badge variant="warning" className="ml-1">
                    algunos sin URL final
                  </Badge>
                )}
              </div>
            </>
          )}
        </div>
      </PageShell>

      <ChannelFormDialog
        open={editing}
        onOpenChange={setEditing}
        channel={channel ?? undefined}
        onSaved={() => {
          setEditing(false);
          load();
        }}
      />

      <ConfirmDialog
        open={!!deletingVideo}
        onOpenChange={(o) => !o && setDeletingVideo(null)}
        title="¿Eliminar este video del historial?"
        description={truncate(deletingVideo?.title, 120)}
        confirmLabel="Eliminar"
        variant="destructive"
        onConfirm={handleDeleteVideo}
      />

      <ConfirmDialog
        open={clearing}
        onOpenChange={setClearing}
        title="¿Vaciar todo el historial?"
        description={`Se borrarán ${videos.length} entradas del caché de este canal. No afecta los videos ya subidos a YouTube.`}
        confirmLabel="Vaciar todo"
        variant="destructive"
        onConfirm={handleClear}
      />

      <ProgressDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        title="Subiendo último video generado a YouTube"
        description="Selenium controla Firefox para subir el video."
        sseUrl={uploadOpen && id ? api.uploadLastUrl(id) : null}
        onDone={load}
      />

      <ProgressDialog
        open={syncing}
        onOpenChange={(o) => {
          setSyncing(o);
          if (!o) load();
        }}
        title="Sincronizando este canal con YouTube"
        description="Reclasifica short/long, agrega los que faltan, borra los huérfanos y actualiza descripción + fecha real de subida."
        sseUrl={syncing && id ? api.syncYouTubeUrl({ channel_id: id, prune: true, add_missing: true, refresh_meta: true }) : null}
      />

      <Dialog open={!!editingVideo} onOpenChange={(o) => !o && setEditingVideo(null)}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Editar entrada del historial</DialogTitle>
            <DialogDescription>
              Solo afecta al caché local — no actualiza el video en YouTube.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="edit-kind">Tipo</Label>
              <Select
                value={editIsShort ? "short" : "long"}
                onValueChange={(v) => setEditIsShort(v === "short")}
              >
                <SelectTrigger id="edit-kind" className="w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="short">Short (9:16)</SelectItem>
                  <SelectItem value="long">Long (16:9)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-title">Título</Label>
              <Input
                id="edit-title"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-subject">Subject</Label>
              <Textarea
                id="edit-subject"
                rows={2}
                value={editSubject}
                onChange={(e) => setEditSubject(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-description">Descripción</Label>
              <Textarea
                id="edit-description"
                rows={4}
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
              />
            </div>
            {editingVideo?.url && (
              <div className="text-[11px] text-muted-foreground font-mono break-all">
                {editingVideo.url}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingVideo(null)}>
              Cancelar
            </Button>
            <Button variant="brand" onClick={saveVideoEdits} disabled={savingVideo}>
              {savingVideo ? "Guardando…" : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function KindTab({
  active,
  onClick,
  icon: Icon,
  label,
  count,
}: {
  active: boolean;
  onClick: () => void;
  icon?: typeof Sparkles;
  label: string;
  count: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "px-2.5 py-1.5 rounded-md text-xs font-medium flex items-center gap-1.5 transition-colors " +
        (active
          ? "bg-background shadow-sm text-foreground"
          : "text-muted-foreground hover:text-foreground")
      }
    >
      {Icon && <Icon className="h-3.5 w-3.5" />}
      {label}
      <span className="tabular-nums opacity-60">({count})</span>
    </button>
  );
}

function VideoRow({
  video,
  onOpen,
  onDelete,
}: {
  video: ChannelVideo;
  onOpen: () => void;
  onDelete: () => void;
}) {
  const isShort = video.is_short;
  const accentVar = isShort ? "var(--primary)" : "var(--violeta)";
  const hasViews = (video.view_count ?? -1) >= 0;
  const hasLikes = (video.like_count ?? -1) >= 0;
  const hasDislikes = (video.dislike_count ?? -1) >= 0;
  const hasComments = (video.comment_count ?? -1) >= 0;
  const hasAnyEngagement = hasViews || hasLikes || hasDislikes || hasComments;

  return (
    <div
      className="group relative grid items-center gap-4 px-5 py-3 transition-colors hover:bg-[hsl(var(--bg-raised)/.5)]"
      style={{
        gridTemplateColumns: "72px minmax(0,2.2fr) minmax(0,1.4fr) 130px minmax(0,1fr) 100px",
        borderTop: "1px solid hsl(var(--border) / .04)",
      }}
    >
      {/* Accent stripe on the left — brightens on hover */}
      <span
        aria-hidden
        className="absolute left-0 top-0 bottom-0 w-[3px] opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ background: `hsl(${accentVar})` }}
      />

      {/* Tipo */}
      <div>
        <span
          className="font-mono uppercase text-[9.5px] font-semibold px-1.5 py-0.5 rounded inline-flex items-center gap-1"
          style={{
            letterSpacing: "0.14em",
            color: `hsl(${accentVar})`,
            background: `hsl(${accentVar} / .10)`,
            border: `1px solid hsl(${accentVar} / .25)`,
          }}
        >
          {isShort ? (
            <Sparkles className="h-2.5 w-2.5" strokeWidth={2} />
          ) : (
            <Clapperboard className="h-2.5 w-2.5" strokeWidth={2} />
          )}
          {isShort ? "Short" : "Long"}
        </span>
      </div>

      {/* Título + descripción */}
      <div className="min-w-0">
        <div className="font-medium text-[13.5px] text-foreground line-clamp-1 tracking-tight">
          {video.title || "(sin título)"}
        </div>
        {video.description && (
          <div className="text-[11px] text-muted-foreground line-clamp-1 mt-0.5">
            {truncate(video.description, 120)}
          </div>
        )}
      </div>

      {/* Subject (xl+) */}
      <div className="min-w-0 hidden xl:block">
        <div className="text-[11.5px] text-muted-foreground line-clamp-2 leading-snug">
          {video.subject || "—"}
        </div>
      </div>

      {/* Fecha */}
      <div className="hidden lg:block">
        <div className="font-mono text-[11px] text-foreground tabular-nums flex items-center gap-1.5">
          <Calendar className="h-3 w-3 text-muted-foreground" strokeWidth={1.5} />
          {formatDate(video.date)}
        </div>
        <div className="text-[10.5px] text-muted-foreground mt-0.5 ml-[18px]">
          {relativeTime(video.date)}
        </div>
      </div>

      {/* Engagement */}
      <div className="hidden xl:flex items-center gap-3 text-[11px] font-mono text-muted-foreground whitespace-nowrap">
        {hasAnyEngagement ? (
          <>
            {hasViews && (
              <span className="inline-flex items-center gap-1" title="Visualizaciones">
                <Eye className="h-3 w-3" strokeWidth={1.5} />
                <span className="tabular-nums text-foreground">
                  {formatCount(video.view_count)}
                </span>
              </span>
            )}
            {hasLikes && (
              <span className="inline-flex items-center gap-1" title="Me gusta">
                <ThumbsUp className="h-3 w-3" strokeWidth={1.5} />
                <span className="tabular-nums text-foreground">
                  {formatCount(video.like_count)}
                </span>
              </span>
            )}
            {hasDislikes && (
              <span
                className="inline-flex items-center gap-1"
                title="No me gusta (estimado por Return YouTube Dislike)"
              >
                <ThumbsDown className="h-3 w-3" strokeWidth={1.5} />
                <span className="tabular-nums text-foreground">
                  {formatCount(video.dislike_count)}
                </span>
              </span>
            )}
            {hasComments && (
              <span className="inline-flex items-center gap-1" title="Comentarios">
                <MessageSquare className="h-3 w-3" strokeWidth={1.5} />
                <span className="tabular-nums text-foreground">
                  {formatCount(video.comment_count)}
                </span>
              </span>
            )}
          </>
        ) : (
          <span className="text-muted-foreground/60 italic">sin datos</span>
        )}
      </div>

      {/* Acciones */}
      <div className="flex items-center justify-end gap-0.5">
        {video.url && video.url.startsWith("http") && (
          <a href={video.url} target="_blank" rel="noreferrer">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 opacity-70 hover:opacity-100"
              aria-label="Abrir en YouTube"
              title="Abrir en YouTube"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </Button>
          </a>
        )}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 opacity-70 hover:opacity-100"
          onClick={onOpen}
          aria-label="Editar"
          title="Editar título y subject"
        >
          <Pencil className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground hover:text-destructive opacity-70 hover:opacity-100"
          onClick={onDelete}
          aria-label="Eliminar"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

function SummaryItem({
  label,
  value,
  dotVar,
  last,
  hint,
  fullValue,
  highlight,
}: {
  label: string;
  value: string;
  dotVar: string;
  last?: boolean;
  hint?: string;
  // Optional precise number (e.g. "12,345") shown below the compact value
  // when the field is a metric — `formatCompact` rounds aggressively.
  fullValue?: string;
  // When true, render the value in the accent color (used for the subscriber
  // count to draw the eye to the most important channel KPI).
  highlight?: boolean;
}) {
  return (
    <div
      className="px-[18px] py-3.5 flex flex-col gap-1 min-w-0"
      style={{
        borderRight: last ? undefined : "1px solid hsl(var(--border) / .04)",
      }}
      title={hint || value}
    >
      <div className="flex items-center gap-1.5">
        <span
          className="w-1.5 h-1.5 rounded-full shrink-0"
          style={{ background: `hsl(${dotVar})` }}
        />
        <span
          className="font-mono uppercase text-[10px] font-semibold text-muted-foreground"
          style={{ letterSpacing: "0.18em" }}
        >
          {label}
        </span>
      </div>
      <span
        className={
          "font-mono text-[15px] font-semibold tracking-tight tabular-nums truncate " +
          (highlight ? "text-primary" : "text-foreground")
        }
      >
        {value}
      </span>
      {fullValue && fullValue !== value && (
        <span className="font-mono text-[10px] text-muted-foreground tabular-nums truncate">
          {fullValue}
        </span>
      )}
    </div>
  );
}

function StatCell({ value }: { value: number | null | undefined }) {
  // `null` (never synced) is rendered muted. Real zeros stay full opacity so
  // a synced-but-no-views video doesn't look like missing data.
  const muted = value == null;
  return (
    <span
      className={
        "text-xs " +
        (muted ? "text-muted-foreground/60" : "text-foreground font-medium")
      }
      title={value == null ? "Sin sincronizar" : String(value)}
    >
      {formatCompact(value)}
    </span>
  );
}
