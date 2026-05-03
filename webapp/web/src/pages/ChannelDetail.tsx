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
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { formatDate, relativeTime, truncate } from "@/lib/utils";

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

        {/* Channel summary card */}
        {channel && !loading ? (
          <Card>
            <CardContent className="p-5 flex flex-wrap items-center gap-x-8 gap-y-3">
              <SummaryItem label="Videos" value={`${channel.videos_count}`} />
              <SummaryItem label="Idioma" value={channel.language || "—"} />
              <SummaryItem
                label="Voz short"
                value={channel.short_voice || "default"}
              />
              <SummaryItem label="Voz long" value={channel.long_voice || "default"} />
              <SummaryItem
                label="Estilo"
                value={truncate(channel.image_style, 32) || "default"}
              />
              <SummaryItem
                label="Hook profile"
                value={channel.hook_profile || "default"}
              />
            </CardContent>
          </Card>
        ) : (
          <Skeleton className="h-[80px]" />
        )}

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0 gap-4 flex-wrap">
            <div>
              <CardTitle>Historial de videos</CardTitle>
              <p className="text-sm text-muted-foreground mt-1">
                Lista de videos generados y registrados en el caché.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <div className="inline-flex rounded-lg border border-border/60 p-0.5 bg-muted/30">
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
          </CardHeader>

          <CardContent>
            {loading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-16" />
                ))}
              </div>
            ) : filtered.length === 0 ? (
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
            ) : (
              <div className="overflow-hidden rounded-lg border border-border/60">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium w-20">Tipo</th>
                      <th className="text-left px-4 py-2 font-medium">Título</th>
                      <th className="text-left px-4 py-2 font-medium hidden md:table-cell">Subject</th>
                      <th className="text-left px-4 py-2 font-medium hidden lg:table-cell">Fecha</th>
                      <th className="text-right px-4 py-2 font-medium">Acciones</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {filtered.map((v) => (
                      <tr key={v.index} className="hover:bg-muted/30 transition-colors">
                        <td className="px-3 py-3">
                          {v.is_short ? (
                            <Badge variant="outline" className="gap-1 text-emerald-300 border-emerald-300/40 bg-emerald-300/5">
                              <Sparkles className="h-3 w-3" /> Short
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="gap-1 text-violet-300 border-violet-300/40 bg-violet-300/5">
                              <Clapperboard className="h-3 w-3" /> Long
                            </Badge>
                          )}
                        </td>
                        <td className="px-4 py-3 max-w-[400px]">
                          <div className="font-medium text-foreground line-clamp-1">
                            {v.title || "(sin título)"}
                          </div>
                          <div className="text-xs text-muted-foreground line-clamp-1 mt-0.5">
                            {truncate(v.description, 120)}
                          </div>
                        </td>
                        <td className="px-4 py-3 max-w-[280px] hidden md:table-cell">
                          <div className="text-xs text-muted-foreground line-clamp-2">
                            {v.subject || "—"}
                          </div>
                        </td>
                        <td className="px-4 py-3 hidden lg:table-cell">
                          <div className="flex items-center gap-1.5 text-xs">
                            <Calendar className="h-3 w-3 text-muted-foreground" />
                            <span>{formatDate(v.date)}</span>
                          </div>
                          <div className="text-[11px] text-muted-foreground mt-0.5">
                            {relativeTime(v.date)}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-1">
                            {v.url && v.url.startsWith("http") && (
                              <a href={v.url} target="_blank" rel="noreferrer">
                                <Button variant="ghost" size="icon" aria-label="Abrir">
                                  <ExternalLink className="h-4 w-4" />
                                </Button>
                              </a>
                            )}
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => openEditVideo(v)}
                              aria-label="Editar"
                              title="Editar título y subject"
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => setDeletingVideo(v)}
                              className="text-muted-foreground hover:text-destructive"
                              aria-label="Eliminar"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="px-4 py-2 text-xs text-muted-foreground border-t border-border/60 bg-muted/30">
                  Mostrando {filtered.length} de {videos.length} videos
                  {videos.some((v) => !v.url || !v.url.startsWith("http")) && (
                    <span className="ml-2">
                      <Badge variant="warning" className="ml-1">
                        algunos sin URL final
                      </Badge>
                    </span>
                  )}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
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

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
        {label}
      </div>
      <div className="text-sm font-medium mt-0.5">{value}</div>
    </div>
  );
}
