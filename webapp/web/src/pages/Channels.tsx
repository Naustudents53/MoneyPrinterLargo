import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Plus,
  Pencil,
  Trash2,
  Youtube,
  Search,
  ChevronRight,
  RefreshCw,
  Users,
  ArrowUpRight,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ProgressDialog } from "@/components/ProgressDialog";
import { api, type Channel, type ChannelVideo } from "@/lib/api";
import { ChannelFormDialog } from "./ChannelFormDialog";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { toast } from "sonner";
import { cn, relativeTime, truncate, formatCompact } from "@/lib/utils";

// Cycle channel accent through the design's 5 brand stops so each card
// reads with a distinct colour band even when the API doesn't supply one.
const ACCENT_VARS = [
  "var(--primary)",
  "var(--accent)",
  "var(--gold)",
  "var(--lima)",
  "var(--violeta)",
] as const;

export function Channels() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Channel | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<Channel | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [filter, setFilter] = useState("");

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

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return channels;
    return channels.filter((c) =>
      [c.nickname, c.niche, c.language].some((v) => (v || "").toLowerCase().includes(q)),
    );
  }, [channels, filter]);

  const totalVideos = channels.reduce((acc, c) => acc + c.videos_count, 0);

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
        eyebrow="Canales"
        title="YouTube"
        description="Tu rack de canales activos"
        actions={
          <div className="flex items-center gap-2 flex-wrap justify-end">
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={() => setSyncing(true)}
              title="Sincroniza el historial local con los videos reales de tus canales en YouTube"
            >
              <RefreshCw className="h-4 w-4" /> Sincronizar
            </Button>
          </div>
        }
      />

      <PageShell>
        <section className="page-hero">
          <div className="page-hero-inner">
            <div>
              <span className="eyebrow block mb-2">YouTube studio</span>
              <h1 className="page-title">
                Tu rack de <span className="brand-text">canales</span>
              </h1>
              <p className="page-subtitle">
                {channels.length} canales activos, {totalVideos} videos en historial y
                sincronizacion directa con YouTube.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap justify-end w-full sm:w-auto">
              <div className="command-strip flex h-10 min-w-0 flex-1 sm:w-72 sm:flex-none items-center gap-2 rounded-xl px-3 text-muted-foreground">
                <Search className="h-4 w-4 shrink-0" />
                <input
                  placeholder="Filtrar por canal o nicho..."
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  className="min-w-0 flex-1 bg-transparent border-0 outline-none text-foreground text-[13px] placeholder:text-muted-foreground"
                />
              </div>
              <Button
                variant="brand"
                size="sm"
                className="h-10 gap-2"
                onClick={() => setCreating(true)}
              >
                <Plus className="h-4 w-4" /> Nuevo canal
              </Button>
            </div>
          </div>
        </section>

        {/* Grid */}
        {loading ? (
          <div className="app-card-grid">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-[286px]" />
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
        ) : visible.length === 0 ? (
          <EmptyState
            icon={Search}
            title="Sin coincidencias"
            description="Prueba con otro canal, nicho o idioma."
          />
        ) : (
          <div className="app-card-grid">
            {visible.map((c, i) => (
              <ChannelCard
                key={c.id}
                channel={c}
                accentVar={ACCENT_VARS[i % ACCENT_VARS.length]}
                onEdit={() => setEditing(c)}
                onDelete={() => setDeleting(c)}
              />
            ))}
            <NewChannelCard onClick={() => setCreating(true)} />
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
        sseUrl={
          syncing
            ? api.syncYouTubeUrl({ prune: true, add_missing: true, refresh_meta: true })
            : null
        }
      />
    </>
  );
}
// ─────────────────────────────────────────────────────────────────────────────
// ChannelCard
// ─────────────────────────────────────────────────────────────────────────────
function ChannelCard({
  channel,
  accentVar,
  onEdit,
  onDelete,
}: {
  channel: Channel;
  accentVar: string;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const [videos, setVideos] = useState<ChannelVideo[] | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .listVideos(channel.id)
      .then((vids) => alive && setVideos(vids.slice(0, 3)))
      .catch(() => alive && setVideos([]));
    return () => {
      alive = false;
    };
  }, [channel.id]);

  const recent = (videos ?? []).slice(0, 3);
  const last = videos?.[0];
  const shortCount = (videos ?? []).filter((v) => v.is_short).length;
  const longCount = (videos ?? []).length - shortCount;
  const flag = flagFromLang(channel.language);
  const voiceShort = compactVoice(channel.short_voice || channel.long_voice || "");
  const initial = (channel.nickname || "?").slice(0, 1).toUpperCase();
  // Subscriber count surfaced by sync_youtube_cache.py — null = never synced.
  const subs = channel.subscriber_count;

  return (
    <div
      className="studio-surface studio-hover overflow-hidden flex flex-col group relative"
      style={{ background: "hsl(var(--card))" }}
    >
      {/* Top accent stripe */}
      <span
        aria-hidden
        className="absolute top-0 left-0 right-0"
        style={{ height: 3, background: `hsl(${accentVar})`, opacity: 0.85 }}
      />
      {/* Top wash */}
      <div
        aria-hidden
        className="absolute inset-x-0 top-0 h-20 pointer-events-none"
        style={{
          background: `linear-gradient(135deg, hsl(${accentVar} / .13), transparent 62%)`,
        }}
      />

      {/* Action overlay (edit/delete) — visible on hover, top-right */}
      <div className="absolute top-3 right-3 z-10 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 bg-card/80 backdrop-blur"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onEdit();
          }}
          aria-label="Editar canal"
        >
          <Pencil className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 bg-card/80 backdrop-blur text-muted-foreground hover:text-destructive"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onDelete();
          }}
          aria-label="Eliminar canal"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>

      <Link to={`/channels/${channel.id}`} className="flex flex-col relative">
        {/* Identity row */}
        <div className="px-[18px] pt-[22px] pb-3.5 flex items-start gap-3.5">
          <div
            className="w-[54px] h-[54px] rounded-[10px] flex items-center justify-center shrink-0 relative overflow-hidden"
            style={{
              background: `linear-gradient(135deg, color-mix(in oklch, hsl(${accentVar}) 35%, hsl(var(--background))), hsl(var(--background)))`,
              border: `1px solid color-mix(in oklch, hsl(${accentVar}) 30%, hsl(var(--border) / .12))`,
            }}
          >
            <span
              className="font-display font-bold leading-none"
              style={{
                color: `hsl(${accentVar})`,
                fontSize: 24,
                letterSpacing: "0",
              }}
            >
              {initial}
            </span>
            <div
              aria-hidden
              className="absolute inset-0 opacity-10"
              style={{
                color: `hsl(${accentVar})`,
                backgroundImage:
                  "repeating-linear-gradient(45deg, currentColor 0, currentColor 1px, transparent 0, transparent 6px)",
              }}
            />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 mb-0.5">
              <span className="font-display text-[16px] font-semibold text-foreground truncate">
                {channel.nickname}
              </span>
              {flag && (
                <span className="font-mono text-[11px] text-muted-foreground">{flag}</span>
              )}
            </div>
            <div className="text-[12px] text-muted-foreground truncate">
              {channel.niche || "(sin niche definido)"}
            </div>
          </div>
        </div>

        {/* Telemetry strip — shorts / longs / último */}
        <div className="metric-strip grid-cols-3 mx-[18px]">
          <ChannelStat label="Shorts" value={shortCount} accentVar="var(--primary)" />
          <ChannelStat
            label="Largos"
            value={longCount}
            accentVar="var(--violeta)"
            withDivider
          />
          <ChannelStat
            label="Último"
            value={last ? relativeTime(last.date).replace("hace ", "") : "—"}
            accentVar="var(--gold)"
            withDivider
            small
          />
        </div>

        {/* Recent videos list */}
        <div className="px-[18px] pt-3.5 pb-3.5 flex flex-col">
          <span className="eyebrow text-muted-foreground mb-2">Recientes</span>
          {videos === null ? (
            <div className="flex flex-col gap-1.5">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-[26px]" />
              ))}
            </div>
          ) : recent.length === 0 ? (
            <div
              className="text-[11.5px] text-muted-foreground py-2 px-2 rounded-md text-center"
              style={{ border: "1px dashed hsl(var(--border) / .12)" }}
            >
              Sin vídeos aún
            </div>
          ) : (
            <div className="flex flex-col">
              {recent.map((v, i) => (
                <RecentVideoRow
                  key={`${v.url || i}-${i}`}
                  video={v}
                  first={i === 0}
                />
              ))}
              {recent.length < 3 &&
                Array.from({ length: 3 - recent.length }).map((_, i) => (
                  <div
                    key={`pad-${i}`}
                    className="h-[26px]"
                    style={{ borderTop: "1px solid hsl(var(--border) / .04)" }}
                  />
                ))}
            </div>
          )}
        </div>

        {/* Footer meta */}
        <div
          className="flex items-center gap-2 px-[18px] py-2.5 mt-auto"
          style={{
            borderTop: "1px solid hsl(var(--border) / .04)",
            background: "hsl(var(--bg-raised) / .4)",
          }}
        >
          <span className="font-mono text-[10.5px] text-foreground">
            {channel.videos_count}{" "}
            <span className="text-muted-foreground">vids</span>
          </span>
          <span className="text-muted-foreground text-[10.5px]">·</span>
          <span
            className="font-mono text-[10.5px] flex items-center gap-1"
            title={
              channel.stats_synced_at
                ? `Sincronizado: ${channel.stats_synced_at}`
                : "Sin sincronizar — corre Sync YT o activa auto-sync"
            }
          >
            <Users className="h-3 w-3 text-muted-foreground" />
            <span className={subs == null ? "text-muted-foreground/60" : "text-foreground"}>
              {formatCompact(subs)}
            </span>
          </span>
          {voiceShort && (
            <>
              <span className="text-muted-foreground text-[10.5px]">·</span>
              <span
                className="font-mono px-1.5 py-px rounded text-[10px] truncate max-w-[120px]"
                style={{
                  border: "1px solid hsl(var(--border) / .12)",
                  color: "hsl(var(--muted-foreground))",
                }}
                title={voiceShort}
              >
                {voiceShort}
              </span>
            </>
          )}
          <span className="ml-auto flex items-center gap-1 text-[11px] text-muted-foreground group-hover:text-foreground transition-colors">
            Ver canal <ChevronRight className="h-3.5 w-3.5" />
          </span>
        </div>
      </Link>
    </div>
  );
}

function ChannelStat({
  label,
  value,
  accentVar,
  withDivider,
  small,
}: {
  label: string;
  value: string | number;
  accentVar: string;
  withDivider?: boolean;
  small?: boolean;
}) {
  return (
    <div
      className="px-2.5 py-2 flex flex-col gap-0.5"
      style={{
        borderLeft: withDivider ? "1px solid hsl(var(--border) / .06)" : undefined,
      }}
    >
      <div className="flex items-center gap-1">
        <span
          className="w-1 h-1 rounded-full"
          style={{ background: `hsl(${accentVar})` }}
        />
        <span
          className="font-mono uppercase text-[9px] font-semibold text-muted-foreground"
          style={{ letterSpacing: "0" }}
        >
          {label}
        </span>
      </div>
      <span
        className={cn(
          "font-mono font-semibold tabular-nums text-foreground truncate",
          small ? "text-[12px]" : "text-[15px]",
        )}
        title={`${value}`}
      >
        {value}
      </span>
    </div>
  );
}

function RecentVideoRow({ video, first }: { video: ChannelVideo; first: boolean }) {
  const isShort = video.is_short;
  return (
    <div
      className="flex items-center gap-2 py-1.5 min-w-0"
      style={{
        borderTop: first ? undefined : "1px solid hsl(var(--border) / .04)",
      }}
    >
      <span
        className="font-mono uppercase text-[8.5px] font-semibold px-1 py-px rounded shrink-0"
        style={{
          letterSpacing: "0",
          color: isShort ? "hsl(var(--primary))" : "hsl(var(--violeta))",
          background: isShort
            ? "hsl(var(--primary) / .10)"
            : "hsl(var(--violeta) / .10)",
          border: `1px solid ${
            isShort ? "hsl(var(--primary) / .25)" : "hsl(var(--violeta) / .25)"
          }`,
        }}
      >
        {isShort ? "SH" : "LG"}
      </span>
      <span className="text-[11.5px] text-foreground truncate flex-1 min-w-0">
        {video.title || "(sin título)"}
      </span>
    </div>
  );
}

function NewChannelCard({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "min-h-[286px] rounded-xl text-muted-foreground flex flex-col items-center justify-center gap-2.5 transition-all",
        "soft-panel hover:text-primary hover:bg-primary/[0.06]",
      )}
      style={{ borderStyle: "dashed" }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = "hsl(var(--primary) / .35)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "hsl(var(--border) / .12)";
      }}
    >
      <span
        className="w-[46px] h-[46px] rounded-full flex items-center justify-center"
        style={{ border: "1.5px dashed currentColor" }}
      >
        <Plus className="h-5 w-5" />
      </span>
      <span className="text-[13px] font-medium">Nuevo canal</span>
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
function flagFromLang(lang: string): string {
  const l = (lang || "").toLowerCase();
  if (!l) return "";
  if (l.includes("mx")) return "MX";
  if (l.includes("es") || l.includes("español")) return "ES";
  if (l.includes("ar")) return "AR";
  if (l.includes("co")) return "CO";
  if (l.includes("us") || l.includes("en")) return "US";
  return "";
}

function compactVoice(voice: string): string {
  if (!voice) return "";
  return voice
    .replace(/Neural$/i, "")
    .replace(/^es-ES-/i, "")
    .replace(/^es-MX-/i, "")
    .replace(/^en-US-/i, "");
}
