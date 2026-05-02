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
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
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
  const [editing, setEditing] = useState(false);
  const [deletingVideo, setDeletingVideo] = useState<ChannelVideo | null>(null);
  const [clearing, setClearing] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);

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

  const filtered = videos.filter(
    (v) =>
      !search ||
      v.title.toLowerCase().includes(search.toLowerCase()) ||
      v.subject.toLowerCase().includes(search.toLowerCase())
  );

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
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Buscar por título o tema…"
                  className="pl-8 h-9 w-72"
                />
              </div>
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
                      <th className="text-left px-4 py-2 font-medium">Título</th>
                      <th className="text-left px-4 py-2 font-medium hidden md:table-cell">Subject</th>
                      <th className="text-left px-4 py-2 font-medium hidden lg:table-cell">Fecha</th>
                      <th className="text-right px-4 py-2 font-medium">Acciones</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {filtered.map((v) => (
                      <tr key={v.index} className="hover:bg-muted/30 transition-colors">
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
    </>
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
