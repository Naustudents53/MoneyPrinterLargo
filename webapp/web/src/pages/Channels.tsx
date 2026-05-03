import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Plus,
  Pencil,
  Trash2,
  Youtube,
  Sparkles,
  Mic,
  ExternalLink,
  Folder,
  RefreshCw,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ProgressDialog } from "@/components/ProgressDialog";
import { api, type Channel } from "@/lib/api";
import { ChannelFormDialog } from "./ChannelFormDialog";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { toast } from "sonner";

export function Channels() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Channel | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<Channel | null>(null);
  const [syncing, setSyncing] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.listChannels();
      setChannels(data);
    } catch (e) {
      toast.error(`No se pudieron cargar los canales: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await api.deleteChannel(deleting.id);
      toast.success(`Canal "${deleting.nickname}" eliminado`);
      setDeleting(null);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <>
      <Header
        title="Canales de YouTube"
        description="Administra los perfiles de cada canal: voces, estilo, niche."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={() => setSyncing(true)}
              title="Sincroniza el historial local con los videos reales de tus canales en YouTube"
            >
              <RefreshCw className="h-4 w-4" /> Sincronizar con YouTube
            </Button>
            <Button variant="brand" size="sm" className="gap-2" onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" /> Nuevo canal
            </Button>
          </div>
        }
      />

      <PageShell>
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-[220px]" />
            ))}
          </div>
        ) : channels.length === 0 ? (
          <EmptyState
            icon={Youtube}
            title="Aún no tienes canales"
            description="Crea tu primer canal de YouTube. Después podrás generar shorts y videos largos."
            action={
              <Button variant="brand" onClick={() => setCreating(true)} className="gap-2">
                <Plus className="h-4 w-4" /> Crear canal
              </Button>
            }
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {channels.map((c) => (
              <ChannelCard
                key={c.id}
                channel={c}
                onEdit={() => setEditing(c)}
                onDelete={() => setDeleting(c)}
              />
            ))}
          </div>
        )}
      </PageShell>

      <ChannelFormDialog
        open={creating}
        onOpenChange={setCreating}
        onSaved={() => {
          setCreating(false);
          load();
        }}
      />

      <ChannelFormDialog
        open={!!editing}
        onOpenChange={(o) => !o && setEditing(null)}
        channel={editing ?? undefined}
        onSaved={() => {
          setEditing(null);
          load();
        }}
      />

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`¿Eliminar "${deleting?.nickname}"?`}
        description="Esta acción borra el canal y su historial de videos en el caché local. No se puede deshacer."
        confirmLabel="Eliminar canal"
        variant="destructive"
        onConfirm={handleDelete}
      />

      <ProgressDialog
        open={syncing}
        onOpenChange={(o) => {
          setSyncing(o);
          if (!o) load();
        }}
        title="Sincronizando con YouTube"
        description="Actualiza tipo (short/long), descripción y fecha de subida de cada video desde tus canales reales. Tarda ~1 min por canal grande."
        sseUrl={syncing ? api.syncYouTubeUrl({ prune: true, add_missing: true, refresh_meta: true }) : null}
      />
    </>
  );
}

function ChannelCard({
  channel,
  onEdit,
  onDelete,
}: {
  channel: Channel;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <Card className="group overflow-hidden hover:border-primary/40 hover:shadow-md transition-all">
      <div className="h-2 bg-brand-gradient" />
      <CardContent className="p-5 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div className="rounded-lg bg-primary/15 p-2 text-primary shrink-0">
                <Youtube className="h-4 w-4" />
              </div>
              <h3 className="font-semibold truncate">{channel.nickname}</h3>
            </div>
            <p className="mt-2 text-sm text-muted-foreground line-clamp-2">
              {channel.niche || "(sin niche definido)"}
            </p>
          </div>
          <Badge variant="outline">{channel.videos_count} videos</Badge>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <Field icon={Sparkles} label="Estilo" value={channel.image_style || "default"} />
          <Field
            icon={Mic}
            label="Voz short"
            value={channel.short_voice || "default"}
          />
          <Field icon={Mic} label="Voz long" value={channel.long_voice || "default"} />
          <Field icon={Folder} label="Idioma" value={channel.language || "es"} />
        </div>

        <div className="flex items-center justify-between gap-2 pt-2 border-t border-border/60">
          <Button asChild variant="ghost" size="sm" className="gap-1.5">
            <Link to={`/channels/${channel.id}`}>
              Ver videos <ExternalLink className="h-3 w-3" />
            </Link>
          </Button>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={onEdit}
              aria-label="Editar canal"
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={onDelete}
              className="text-muted-foreground hover:text-destructive"
              aria-label="Eliminar canal"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function Field({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Sparkles;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-1.5 min-w-0 rounded-md bg-muted/50 px-2 py-1.5">
      <Icon className="h-3 w-3 text-muted-foreground shrink-0" />
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {label}
        </div>
        <div className="text-xs font-medium truncate">{value}</div>
      </div>
    </div>
  );
}
