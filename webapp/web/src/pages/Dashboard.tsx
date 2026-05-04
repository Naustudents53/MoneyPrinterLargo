import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Youtube,
  Twitter,
  HardDrive,
  Film,
  Sparkles,
  ArrowRight,
  ExternalLink,
  Plus,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { StatCard } from "@/components/StatCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { api, type SystemStats } from "@/lib/api";
import { relativeTime, truncate } from "@/lib/utils";

export function Dashboard() {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    api
      .systemStats()
      .then((d) => alive && setStats(d))
      .catch(() => {})
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <>
      <Header
        title="Dashboard"
        description="Vista general de tu motor de contenido."
        actions={
          <Button asChild variant="brand" size="sm" className="gap-2">
            <Link to="/generate">
              <Sparkles className="h-4 w-4" /> Generar
            </Link>
          </Button>
        }
      />

      <PageShell>
        {/* Hero brand panel */}
        <Card className="overflow-hidden border-border/60 bg-gradient-to-br from-card to-card/50">
          <div className="relative p-6 sm:p-8">
            <div className="absolute inset-0 bg-brand-gradient opacity-[0.07]" />
            <div className="relative flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
              <div className="space-y-2 max-w-2xl">
                <Badge variant="gold" className="font-semibold uppercase tracking-wider">
                  MoneyPrinter Pro · v1.0
                </Badge>
                <h2 className="font-display text-2xl sm:text-3xl font-bold tracking-tight">
                  Tu pipeline de contenido en un solo lugar.
                </h2>
                <p className="text-muted-foreground text-sm sm:text-base">
                  Administra canales de YouTube, cuentas de Twitter, series, generación de
                  shorts y videos largos — todo desde aquí, en tiempo real.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="brand" size="lg" className="gap-2">
                  <Link to="/generate">
                    <Sparkles className="h-4 w-4" /> Generar contenido
                  </Link>
                </Button>
                <Button asChild variant="outline" size="lg" className="gap-2">
                  <Link to="/channels">
                    <Plus className="h-4 w-4" /> Nuevo canal
                  </Link>
                </Button>
              </div>
            </div>
          </div>
        </Card>

        {/* Stats grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {loading ? (
            <>
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-[120px]" />
              ))}
            </>
          ) : stats ? (
            <>
              <StatCard
                label="Canales YouTube"
                value={stats.channels_count}
                hint={`${stats.total_videos} videos generados`}
                icon={Youtube}
                accent="primary"
              />
              <StatCard
                label="Cuentas Twitter"
                value={stats.twitter_accounts_count}
                hint={`${stats.total_posts} tweets posteados`}
                icon={Twitter}
                accent="accent"
              />
              <StatCard
                label="Productos AFM"
                value={stats.products_count}
                hint="Affiliate Marketing"
                icon={Sparkles}
                accent="gold"
              />
              <StatCard
                label="Almacenamiento"
                value={`${stats.mp4_mb} MB`}
                hint={`${stats.mp4_count} archivos .mp4`}
                icon={HardDrive}
                accent="success"
              />
            </>
          ) : null}
        </div>

        {/* Recent + quick links */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card className="lg:col-span-2">
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <div>
                <CardTitle>Videos recientes</CardTitle>
                <p className="text-sm text-muted-foreground mt-1">
                  Últimos videos generados en todos los canales
                </p>
              </div>
              <Button asChild variant="ghost" size="sm" className="gap-1">
                <Link to="/channels">
                  Ver todo <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="space-y-3">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-12" />
                  ))}
                </div>
              ) : stats && stats.recent_videos.length > 0 ? (
                <ul className="divide-y divide-border/60">
                  {stats.recent_videos.map((v, i) => (
                    <li
                      key={i}
                      className="py-3 flex items-center justify-between gap-3 group"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="text-[10px]">
                            {v.channel_nickname}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {relativeTime(v.date)}
                          </span>
                        </div>
                        <div className="text-sm font-medium mt-1 truncate">
                          {truncate(v.title, 100) || "(sin título)"}
                        </div>
                      </div>
                      {v.url && v.url.startsWith("http") && (
                        <a
                          href={v.url}
                          target="_blank"
                          rel="noreferrer"
                          className="opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <Button variant="ghost" size="icon">
                            <ExternalLink className="h-3.5 w-3.5" />
                          </Button>
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  icon={Film}
                  title="Aún no hay videos"
                  description="Genera tu primer short o video largo para verlo aquí."
                  action={
                    <Button asChild variant="brand">
                      <Link to="/generate">Generar el primero</Link>
                    </Button>
                  }
                />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Atajos</CardTitle>
              <p className="text-sm text-muted-foreground mt-1">
                Acciones que probablemente quieras hacer ahora
              </p>
            </CardHeader>
            <CardContent className="space-y-2">
              <ShortcutLink to="/generate" icon={Sparkles} label="Generar nuevo short / video" />
              <ShortcutLink to="/channels" icon={Youtube} label="Administrar canales YouTube" />
              <ShortcutLink to="/twitter" icon={Twitter} label="Administrar cuentas Twitter" />
              <ShortcutLink to="/series" icon={Film} label="Series & plantillas" />
              <ShortcutLink to="/storage" icon={HardDrive} label="Limpiar archivos guardados" />
            </CardContent>
          </Card>
        </div>
      </PageShell>
    </>
  );
}

function ShortcutLink({
  to,
  icon: Icon,
  label,
}: {
  to: string;
  icon: typeof Sparkles;
  label: string;
}) {
  return (
    <Link
      to={to}
      className="flex items-center gap-3 rounded-lg border border-border/60 p-3 text-sm font-medium hover:border-primary/40 hover:bg-primary/5 transition-all group"
    >
      <div className="rounded-md bg-primary/10 p-2 text-primary">
        <Icon className="h-4 w-4" />
      </div>
      <span className="flex-1">{label}</span>
      <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
    </Link>
  );
}
