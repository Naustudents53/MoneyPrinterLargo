import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Youtube,
  Twitter,
  HardDrive,
  Film,
  Sparkles,
  ArrowRight,
  ChevronRight,
  ExternalLink,
  Eye,
  Edit3,
  Mic,
  Image as ImageIcon,
  Upload,
  Check,
  Activity,
  Settings as SettingsIcon,
  ShoppingBag,
  Loader2,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { StatCard, Sparkline } from "@/components/StatCard";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { api, type JobSummary, type SystemInfo, type SystemStats } from "@/lib/api";
import { cn, relativeTime, truncate } from "@/lib/utils";

export function Dashboard() {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.systemStats().catch(() => null),
      api.systemInfo().catch(() => null),
      api.listJobs(false).catch(() => []),
    ]).then(([s, i, j]) => {
      if (!alive) return;
      setStats(s);
      setInfo(i);
      setJobs(j);
      setLoading(false);
    });
    const t = setInterval(async () => {
      try {
        const j = await api.listJobs(false);
        if (alive) setJobs(j);
      } catch {
        /* silent */
      }
    }, 4000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  // ── Derived series — counts of uploads per week for the last 8 weeks.
  //    Empty buckets are 0 so the sparkline still draws a baseline.
  const uploadsSeries = useMemo(() => buildWeeklyUploadsSeries(stats), [stats]);
  const totalRecent = uploadsSeries.reduce((a, b) => a + b, 0);

  return (
    <>
      <Header
        eyebrow="· panel principal"
        title="Dashboard"
        description="Vista general del estudio"
        actions={
          <Button asChild variant="brand" size="sm" className="gap-1.5">
            <Link to="/generate">
              <Sparkles className="h-3.5 w-3.5" /> Generar
            </Link>
          </Button>
        }
      />

      <PageShell>
        {/* HERO EDITORIAL */}
        <HeroEditorial stats={stats} jobs={jobs} info={info} />

        {/* STAT CARDS ROW */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
          {loading ? (
            <>
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-[126px]" />
              ))}
            </>
          ) : stats ? (
            <>
              <StatCard
                label="Vídeos generados"
                value={stats.total_videos}
                hint={`${stats.channels_count} canales activos`}
                icon={Film}
                accent="primary"
                series={uploadsSeries.length ? uploadsSeries : undefined}
              />
              <StatCard
                label="Tweets publicados"
                value={stats.total_posts}
                hint={`${stats.twitter_accounts_count} cuentas`}
                icon={Twitter}
                accent="accent"
              />
              <StatCard
                label="Productos AFM"
                value={stats.products_count}
                hint="Affiliate marketing"
                icon={ShoppingBag}
                accent="gold"
              />
              <StatCard
                label="Almacenamiento"
                value={`${stats.mp4_mb} MB`}
                hint={`${stats.mp4_count} archivos .mp4`}
                icon={HardDrive}
                accent="lima"
              />
            </>
          ) : (
            <div className="col-span-full text-sm text-muted-foreground">
              No se pudo conectar con el backend.
            </div>
          )}
        </div>

        {/* LIVE PIPELINE */}
        <div
          className="studio-surface overflow-hidden"
          style={{ background: "hsl(var(--card))" }}
        >
          <div className="px-5 py-4 flex items-center justify-between">
            <div>
              <span
                className="font-mono uppercase font-semibold text-[10px] tracking-[0.24em]"
                style={{ color: "hsl(var(--warning))" }}
              >
                · pipeline en vivo
              </span>
              <div className="flex items-baseline gap-2.5 mt-1">
                <span className="font-display text-[18px] font-semibold tracking-tight">
                  {jobs.filter((j) => j.status === "running").length} jobs corriendo
                </span>
                <span className="text-xs text-muted-foreground">
                  · click en un job para ver el log en directo
                </span>
              </div>
            </div>
            <Button asChild variant="ghost" size="sm" className="gap-1">
              <Link to="/operations">
                <Eye className="h-3.5 w-3.5" /> Ver operaciones
              </Link>
            </Button>
          </div>

          {jobs.filter((j) => j.status === "running").length === 0 ? (
            <div
              className="px-5 py-8 text-center text-sm text-muted-foreground"
              style={{ borderTop: "1px solid hsl(var(--border) / .04)" }}
            >
              No hay jobs corriendo. Lanza uno desde{" "}
              <Link to="/generate" className="text-primary underline-offset-2 hover:underline">
                Generar contenido
              </Link>
              .
            </div>
          ) : (
            jobs
              .filter((j) => j.status === "running")
              .slice(0, 4)
              .map((j) => <PipelineRow key={j.id} job={j} />)
          )}
        </div>

        {/* RECENT VIDEOS + SHORTCUTS */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3.5">
          <div
            className="lg:col-span-2 studio-surface px-5 py-[18px]"
            style={{ background: "hsl(var(--card))" }}
          >
            <div className="flex items-center justify-between mb-3.5">
              <div>
                <span className="eyebrow text-muted-foreground">Vídeos recientes</span>
                <div className="text-[11px] text-muted-foreground mt-0.5">
                  últimos {stats?.recent_videos.length ?? 0} publicados o en curso ·{" "}
                  {totalRecent} en las últimas 8 sem
                </div>
              </div>
              <Button asChild variant="ghost" size="sm" className="gap-1">
                <Link to="/storage">
                  Ver todos <ChevronRight className="h-3 w-3" />
                </Link>
              </Button>
            </div>

            {loading ? (
              <div className="space-y-2.5">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-[42px]" />
                ))}
              </div>
            ) : stats && stats.recent_videos.length > 0 ? (
              <div>
                {stats.recent_videos.map((v, i) => (
                  <div
                    key={`${v.url}-${v.date}-${i}`}
                    className="flex items-center gap-3.5 py-2.5 group"
                    style={{
                      borderTop:
                        i === 0 ? "none" : "1px solid hsl(var(--border) / .04)",
                    }}
                  >
                    <div
                      className="w-[54px] h-[32px] rounded-md shrink-0 overflow-hidden relative"
                      style={{
                        background:
                          "linear-gradient(135deg, hsl(var(--surface-up)), hsl(var(--surface)))",
                        border: "1px solid hsl(var(--border) / .07)",
                      }}
                    >
                      <div
                        className="absolute inset-0 opacity-30"
                        style={{
                          backgroundImage:
                            "repeating-linear-gradient(45deg, hsl(var(--foreground) / .1) 0, hsl(var(--foreground) / .1) 1px, transparent 0, transparent 50%)",
                          backgroundSize: "5px 5px",
                        }}
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] font-medium tracking-tight text-foreground truncate">
                        {truncate(v.title, 100) || "(sin título)"}
                      </div>
                      <div className="text-[11px] text-muted-foreground mt-0.5 flex gap-2 items-center">
                        <span
                          className="font-mono px-1.5 rounded"
                          style={{
                            border: "1px solid hsl(var(--border) / .12)",
                            color: "hsl(var(--muted-foreground))",
                            fontSize: 9.5,
                          }}
                        >
                          {v.channel_nickname}
                        </span>
                        <span>·</span>
                        <span>{relativeTime(v.date)}</span>
                      </div>
                    </div>
                    {v.url && v.url.startsWith("http") && (
                      <a
                        href={v.url}
                        target="_blank"
                        rel="noreferrer"
                        className="opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <Button variant="ghost" size="icon" className="h-7 w-7">
                          <ExternalLink className="h-3.5 w-3.5" />
                        </Button>
                      </a>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                icon={Film}
                title="Aún no hay vídeos"
                description="Genera tu primer short o vídeo largo para verlo aquí."
                action={
                  <Button asChild variant="brand">
                    <Link to="/generate">Generar el primero</Link>
                  </Button>
                }
              />
            )}
          </div>

          <div
            className="studio-surface px-5 py-[18px]"
            style={{ background: "hsl(var(--card))" }}
          >
            <span className="eyebrow text-muted-foreground block mb-3.5">Atajos</span>
            <div className="flex flex-col gap-1.5">
              <ShortcutLink
                to="/generate"
                icon={Sparkles}
                label="Generar Short"
                kbd="⌘ N"
                accent="primary"
              />
              <ShortcutLink
                to="/twitter"
                icon={Twitter}
                label="Postear tweet"
                kbd="⌘ T"
                accent="accent"
              />
              <ShortcutLink
                to="/settings"
                icon={SettingsIcon}
                label="Editar config"
                kbd="⌘ ,"
                accent="gold"
              />
              <ShortcutLink
                to="/operations"
                icon={Activity}
                label="Ver operaciones"
                kbd="⌘ O"
                accent="lima"
              />
            </div>

            <div
              className="mt-[18px] pt-3.5"
              style={{ borderTop: "1px solid hsl(var(--border) / .04)" }}
            >
              <span className="eyebrow text-muted-foreground block mb-2.5">
                Salud del sistema
              </span>
              <div className="flex flex-col gap-2">
                <HealthRow label="Backend" ok={!!info} value={info ? "online" : "offline"} />
                <HealthRow
                  label="LLM"
                  ok={!!info?.llm_provider}
                  value={info?.llm_provider || "—"}
                />
                <HealthRow
                  label="STT"
                  ok={!!info?.stt_provider}
                  value={info?.stt_provider || "—"}
                />
                <HealthRow
                  label="TTS"
                  ok={!!info?.tts_voice}
                  value={info?.tts_voice || "—"}
                />
                <HealthRow
                  label="Almacenamiento"
                  ok={(stats?.mp4_mb ?? 0) < 50_000}
                  value={
                    stats
                      ? `${stats.mp4_mb} MB · ${stats.mp4_count} archivos`
                      : "—"
                  }
                />
              </div>
            </div>
          </div>
        </div>
      </PageShell>
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Hero
// ─────────────────────────────────────────────────────────────────────────────
function HeroEditorial({
  stats,
  jobs,
  info,
}: {
  stats: SystemStats | null;
  jobs: JobSummary[];
  info: SystemInfo | null;
}) {
  const today = new Date().toLocaleDateString("es-ES", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  const running = jobs.filter((j) => j.status === "running");
  const recent = (stats?.recent_videos ?? []).slice(0, 5);

  return (
    <div
      className="studio-surface relative overflow-hidden"
      style={{
        background: "hsl(var(--card))",
        boxShadow: "0 20px 60px -28px hsl(var(--ink) / .35)",
      }}
    >
      <div
        aria-hidden
        className="absolute inset-0 pointer-events-none opacity-60"
        style={{
          backgroundImage: `radial-gradient(ellipse 60% 90% at 100% 0%, hsl(var(--primary) / .15), transparent 65%),
            radial-gradient(ellipse 50% 70% at 0% 100%, hsl(var(--accent) / .15), transparent 70%)`,
        }}
      />

      {/* Top half — copy + activity */}
      <div className="relative grid grid-cols-1 lg:grid-cols-[1.5fr_1fr] gap-9 px-9 pt-[34px] pb-7">
        <div>
          <span className="eyebrow inline-block mb-3.5">· studio · {today}</span>
          <h2 className="font-display text-[44px] lg:text-[56px] font-semibold tracking-[-0.035em] leading-[1.05] mb-4 text-foreground">
            Imprime largo,
            <br />
            <span className="brand-text">edita poco.</span>
          </h2>
          <p className="text-[15px] text-muted-foreground leading-[1.55] max-w-[520px] mb-5">
            Tu estudio local.{" "}
            <strong className="font-medium text-foreground">
              {stats?.channels_count ?? "—"} canales activos
            </strong>
            , {stats?.total_videos ?? 0} vídeos en historial y {running.length} jobs
            corriendo en segundo plano. Lanza el siguiente desde aquí.
          </p>
          <div className="flex items-center gap-2.5 flex-wrap">
            <Button asChild variant="brand" size="lg" className="gap-2">
              <Link to="/generate">
                <Sparkles className="h-4 w-4" /> Generar contenido
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg" className="gap-2">
              <Link to="/operations">
                <Activity className="h-3.5 w-3.5" /> Ver historial
              </Link>
            </Button>
            <span className="font-mono text-[12px] text-muted-foreground ml-1.5">⌘ + N</span>
          </div>
        </div>

        {/* Activity feed */}
        <div
          className="flex flex-col gap-2.5 pl-6"
          style={{ borderLeft: "1px solid hsl(var(--border) / .07)" }}
        >
          <div className="flex items-center justify-between mb-1">
            <span className="eyebrow text-muted-foreground">Última actividad</span>
            <span className="inline-flex items-center gap-1.5 text-[10px] font-mono text-success uppercase tracking-wider">
              <span className="h-1.5 w-1.5 rounded-full bg-success animate-mpl-pulse" />
              EN VIVO
            </span>
          </div>
          {running.slice(0, 3).map((j) => (
            <ActivityRow
              key={j.id}
              time={new Date(j.started_at).toLocaleTimeString("es-ES", {
                hour: "2-digit",
                minute: "2-digit",
              })}
              text="Job corriendo"
              detail={j.title}
              tag="render"
              colorVar="var(--warning)"
            />
          ))}
          {recent.slice(0, Math.max(0, 5 - running.length)).map((v, i) => (
            <ActivityRow
              key={`r-${i}`}
              time={
                v.date
                  ? relativeTime(v.date).replace("hace ", "h-")
                  : "—"
              }
              text="Vídeo publicado"
              detail={truncate(v.title, 36) || "(sin título)"}
              tag="subida"
              colorVar="var(--primary)"
            />
          ))}
          {running.length === 0 && recent.length === 0 && (
            <div className="text-[12px] text-muted-foreground">Sin actividad reciente.</div>
          )}
        </div>
      </div>

      {/* Bottom telemetry marquee */}
      <div
        className="relative grid grid-cols-2 md:grid-cols-5"
        style={{
          borderTop: "1px solid hsl(var(--border) / .07)",
          background: "hsl(var(--bg-raised) / .6)",
        }}
      >
        <Telemetry
          label="Versión"
          value={info ? `v${info.version}` : "—"}
          detail={info?.headless ? "headless · activo" : "headless · off"}
          dotVar="var(--success)"
        />
        <Telemetry
          label="Disco mp/"
          value={stats ? `${(stats.mp4_bytes / 1024 / 1024 / 1024).toFixed(1)} GB` : "—"}
          detail={stats ? `${stats.mp4_count} archivos .mp4` : "—"}
          dotVar="var(--gold)"
        />
        <Telemetry
          label="LLM"
          value={info?.llm_provider || "—"}
          detail="proveedor activo"
          dotVar="var(--primary)"
        />
        <Telemetry
          label="Voz TTS"
          value={info?.tts_voice || "—"}
          detail={info?.stt_provider ? `STT · ${info.stt_provider}` : "—"}
          dotVar="var(--accent)"
        />
        <Telemetry
          label="Jobs"
          value={`${running.length}/${jobs.length}`}
          detail="corriendo / totales"
          dotVar="var(--lima)"
        />
      </div>
    </div>
  );
}

function ActivityRow({
  time,
  text,
  detail,
  tag,
  colorVar,
}: {
  time: string;
  text: string;
  detail: string;
  tag: string;
  colorVar: string;
}) {
  return (
    <div className="flex items-start gap-2.5 py-1">
      <span className="font-mono text-[10.5px] text-muted-foreground min-w-9 pt-0.5">
        {time}
      </span>
      <span
        className="w-1.5 h-1.5 rounded-full mt-2 shrink-0"
        style={{ background: `hsl(${colorVar})` }}
      />
      <div className="flex-1 min-w-0">
        <div className="text-[12.5px] font-medium tracking-tight text-foreground">
          {text}
        </div>
        <div className="text-[11px] text-muted-foreground mt-px truncate">{detail}</div>
      </div>
      <span
        className="font-mono px-1.5 py-px rounded"
        style={{
          border: "1px solid hsl(var(--border) / .12)",
          color: `hsl(${colorVar})`,
          fontSize: 9.5,
        }}
      >
        {tag}
      </span>
    </div>
  );
}

function Telemetry({
  label,
  value,
  detail,
  dotVar,
}: {
  label: string;
  value: string;
  detail: string;
  dotVar: string;
}) {
  return (
    <div
      className="px-[18px] py-3.5 flex flex-col gap-0.5"
      style={{ borderRight: "1px solid hsl(var(--border) / .04)" }}
    >
      <div className="flex items-center gap-1.5">
        <span
          className="w-1.5 h-1.5 rounded-full"
          style={{ background: `hsl(${dotVar})` }}
        />
        <span
          className="font-mono uppercase text-[10px] font-semibold text-muted-foreground"
          style={{ letterSpacing: "0.18em" }}
        >
          {label}
        </span>
      </div>
      <span className="font-mono text-[18px] font-semibold tracking-tight text-foreground tabular-nums">
        {value}
      </span>
      <span className="text-[11px] text-muted-foreground">{detail}</span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline row
// ─────────────────────────────────────────────────────────────────────────────
const PIPELINE_STAGES: { id: string; label: string; icon: typeof Edit3 }[] = [
  { id: "guion", label: "Guion", icon: Edit3 },
  { id: "tts", label: "TTS", icon: Mic },
  { id: "imagenes", label: "Imágenes", icon: ImageIcon },
  { id: "render", label: "Render", icon: Film },
  { id: "subida", label: "Subida", icon: Upload },
];

function PipelineRow({ job }: { job: JobSummary }) {
  // Heuristic: infer the active stage from the last log line. Falls back to
  // index 0 when nothing matches.
  const last = (job.last_line || "").toLowerCase();
  let activeIdx = 0;
  if (/(subir|upload|youtube studio|firefox)/i.test(last)) activeIdx = 4;
  else if (/(render|moviepy|ffmpeg|export|composici)/i.test(last)) activeIdx = 3;
  else if (/(imagen|nano banana|gemini|prompt)/i.test(last)) activeIdx = 2;
  else if (/(tts|kitten|voz|audio|whisper)/i.test(last)) activeIdx = 1;
  else if (/(guion|script|generar|frase)/i.test(last)) activeIdx = 0;

  const elapsed = formatElapsed(job.elapsed);
  const channelLabel = job.channel_id ? job.channel_id.slice(0, 6) : "—";

  return (
    <div
      className="grid grid-cols-[1fr_auto] gap-4 px-5 py-3.5 items-center"
      style={{ borderTop: "1px solid hsl(var(--border) / .04)" }}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2.5 mb-2">
          <span className="w-2 h-2 rounded-sm bg-primary shrink-0" />
          <span className="text-[13.5px] font-medium tracking-tight truncate">
            {job.title}
          </span>
          <span
            className="font-mono px-1.5 py-px rounded text-[9.5px]"
            style={{
              border: "1px solid hsl(var(--border) / .12)",
              color: "hsl(var(--muted-foreground))",
            }}
          >
            {channelLabel}
          </span>
          <span className="ml-auto font-mono text-[11px] text-muted-foreground">
            elapsed · <span className="text-foreground">{elapsed}</span>
          </span>
        </div>
        <div className="flex items-center">
          {PIPELINE_STAGES.map((s, i) => {
            const done = i < activeIdx;
            const active = i === activeIdx;
            const fg = done
              ? "hsl(var(--success))"
              : active
              ? "hsl(var(--primary))"
              : "hsl(var(--muted-foreground))";
            const Icon = s.icon;
            return (
              <span key={s.id} className="contents">
                <span className="flex items-center gap-1.5 pr-2.5">
                  <span
                    className={cn(
                      "w-[22px] h-[22px] rounded-full flex items-center justify-center shrink-0",
                      active && "animate-mpl-pulse"
                    )}
                    style={{
                      background: active
                        ? "hsl(var(--primary) / .15)"
                        : done
                        ? "hsl(var(--success) / .15)"
                        : "transparent",
                      border: `1px solid ${
                        active
                          ? "hsl(var(--primary))"
                          : done
                          ? "hsl(var(--success))"
                          : "hsl(var(--border) / .12)"
                      }`,
                    }}
                  >
                    {done ? (
                      <Check className="h-3 w-3" style={{ color: fg }} strokeWidth={2} />
                    ) : (
                      <Icon className="h-3 w-3" style={{ color: fg }} strokeWidth={1.5} />
                    )}
                  </span>
                  <span
                    className="text-[11px]"
                    style={{ color: fg, fontWeight: active ? 500 : 400 }}
                  >
                    {s.label}
                  </span>
                </span>
                {i < PIPELINE_STAGES.length - 1 && (
                  <span
                    className="flex-1 h-0.5 rounded mr-2.5"
                    style={{
                      background:
                        i < activeIdx
                          ? "hsl(var(--success))"
                          : "hsl(var(--border) / .07)",
                    }}
                  />
                )}
              </span>
            );
          })}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
        <span className="font-mono text-[11px] text-muted-foreground">
          stage <span className="text-foreground">{PIPELINE_STAGES[activeIdx].label}</span>
        </span>
      </div>
    </div>
  );
}

function ShortcutLink({
  to,
  icon: Icon,
  label,
  kbd,
  accent,
}: {
  to: string;
  icon: typeof Sparkles;
  label: string;
  kbd: string;
  accent: "primary" | "accent" | "gold" | "lima";
}) {
  const accentVar =
    accent === "primary"
      ? "var(--primary)"
      : accent === "accent"
      ? "var(--accent)"
      : accent === "gold"
      ? "var(--gold)"
      : "var(--lima)";
  return (
    <Link
      to={to}
      className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-[13px] font-medium text-foreground hover:bg-surface transition-colors"
      style={{
        background: "hsl(var(--bg-raised))",
        border: "1px solid hsl(var(--border) / .07)",
      }}
    >
      <span
        className="w-6 h-6 rounded-md flex items-center justify-center shrink-0"
        style={{
          background: `hsl(${accentVar} / .14)`,
          border: `1px solid hsl(${accentVar} / .30)`,
        }}
      >
        <Icon className="h-3 w-3" strokeWidth={1.5} style={{ color: `hsl(${accentVar})` }} />
      </span>
      <span className="flex-1">{label}</span>
      <span
        className="font-mono text-[10.5px] text-muted-foreground px-1.5 py-0.5 rounded"
        style={{
          border: "1px solid hsl(var(--border) / .07)",
          background: "hsl(var(--surface))",
        }}
      >
        {kbd}
      </span>
      <ArrowRight
        className="h-3.5 w-3.5 text-muted-foreground"
        strokeWidth={1.5}
      />
    </Link>
  );
}

function HealthRow({ label, ok, value }: { label: string; ok: boolean; value: string }) {
  return (
    <div className="flex items-center gap-2 text-[12px]">
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{
          background: ok ? "hsl(var(--success))" : "hsl(var(--muted-foreground))",
        }}
      />
      <span className="text-muted-foreground flex-1">{label}</span>
      <span className="text-foreground font-mono text-[11px] truncate max-w-[150px]">
        {value}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
function buildWeeklyUploadsSeries(stats: SystemStats | null): number[] {
  if (!stats) return [];
  // Bucket recent_videos into 8 ISO weeks (oldest → newest). Backend exposes
  // up to 8 entries — use them as a rough proxy. If we don't have date data,
  // skip the sparkline entirely.
  const buckets = Array(8).fill(0);
  const now = Date.now();
  const week = 7 * 24 * 3600 * 1000;
  let ok = false;
  for (const v of stats.recent_videos) {
    const d = v.date ? new Date(v.date).getTime() : NaN;
    if (isNaN(d)) continue;
    const diff = now - d;
    if (diff < 0) continue;
    const idx = Math.min(7, Math.floor(diff / week));
    buckets[7 - idx] += 1;
    ok = true;
  }
  return ok ? buckets : [];
}

function formatElapsed(s: number) {
  if (s < 60) return `${s.toFixed(0)}s`;
  const m = Math.floor(s / 60);
  const r = Math.floor(s - m * 60);
  return `${m}m${r}s`;
}

// Re-export so other modules can import the underlying sparkline if needed.
export { Sparkline };
