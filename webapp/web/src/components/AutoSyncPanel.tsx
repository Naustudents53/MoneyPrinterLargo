import { useEffect, useMemo, useRef, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  PlayCircle,
  RefreshCw,
  Users,
  Eye,
  Database,
} from "lucide-react";
import { toast } from "sonner";
import {
  api,
  type AutoSyncConfig,
  type AutoSyncStatus,
  type AutoSyncTier,
  type AutoSyncTierState,
} from "@/lib/api";
import { relativeTime } from "@/lib/utils";
import { cn } from "@/lib/utils";

const POLL_INTERVAL_MS = 5000;

type TierAccent = "lima" | "primary" | "accent";

interface TierDef {
  id: AutoSyncTier;
  eyebrow: string;
  label: string;
  description: string;
  icon: typeof Activity;
  accent: TierAccent;
  enabledKey: keyof AutoSyncConfig;
  intervalKey: keyof AutoSyncConfig;
  minInterval: number;
  maxInterval: number;
  intervalUnit: string;
  hint: string;
}

const TIERS: TierDef[] = [
  {
    id: "light",
    eyebrow: "Liviano",
    label: "Suscriptores",
    description: "Refresca el número de suscriptores de cada canal.",
    icon: Users,
    accent: "lima",
    enabledKey: "light_enabled",
    intervalKey: "light_interval_minutes",
    minInterval: 15,
    maxInterval: 360,
    intervalUnit: "min",
    hint: "1 request por canal. Seguro a alta frecuencia.",
  },
  {
    id: "recent",
    eyebrow: "Medio",
    label: "Stats de videos recientes",
    description: "Refresca views, likes y comentarios de los videos más nuevos.",
    icon: Eye,
    accent: "primary",
    enabledKey: "recent_enabled",
    intervalKey: "recent_interval_minutes",
    minInterval: 10,
    maxInterval: 360,
    intervalUnit: "min",
    hint: "Los recientes mueven más en las primeras 48h.",
  },
  {
    id: "full",
    eyebrow: "Pesado",
    label: "Sync completo",
    description:
      "Equivalente al botón manual Sync YT. Reclasifica short/long, agrega/quita, refresca todo.",
    icon: Database,
    accent: "accent",
    enabledKey: "full_enabled",
    intervalKey: "full_interval_minutes",
    minInterval: 180,
    maxInterval: 1440,
    intervalUnit: "min",
    hint: "~1 min por canal grande. Default off — corre manual cuando lo necesites.",
  },
];

export function AutoSyncPanel() {
  const [status, setStatus] = useState<AutoSyncStatus | null>(null);
  const [draft, setDraft] = useState<AutoSyncConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [triggering, setTriggering] = useState<AutoSyncTier | null>(null);
  const pollTimer = useRef<number | null>(null);

  const fetchStatus = async () => {
    try {
      const s = await api.getAutoSyncStatus();
      setStatus(s);
      // Only seed the draft from server config on the very first load OR
      // when the user has no pending edits — otherwise we'd clobber what
      // they're typing every 5 seconds.
      setDraft((prev) => prev ?? s.config);
    } catch {
      /* swallow — keep stale state visible */
    }
  };

  useEffect(() => {
    fetchStatus();
    pollTimer.current = window.setInterval(fetchStatus, POLL_INTERVAL_MS) as unknown as number;
    return () => {
      if (pollTimer.current) window.clearInterval(pollTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isDirty = useMemo(() => {
    if (!draft || !status) return false;
    const keys: (keyof AutoSyncConfig)[] = [
      "enabled",
      "light_enabled",
      "light_interval_minutes",
      "recent_enabled",
      "recent_interval_minutes",
      "recent_video_count",
      "full_enabled",
      "full_interval_minutes",
    ];
    return keys.some((k) => draft[k] !== status.config[k]);
  }, [draft, status]);

  const patch = (k: keyof AutoSyncConfig, v: AutoSyncConfig[keyof AutoSyncConfig]) => {
    setDraft((prev) => (prev ? { ...prev, [k]: v } : prev));
  };

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const r = await api.updateAutoSyncConfig(draft);
      setDraft(r.auto_sync);
      // Force-refresh status so the new intervals show immediately.
      await fetchStatus();
      toast.success("Configuración de auto-sync guardada");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const triggerTier = async (tier: AutoSyncTier) => {
    setTriggering(tier);
    try {
      await api.triggerAutoSync(tier);
      toast.success(`Sync ${tier} disparado — corre en unos segundos`);
      // Re-poll quickly to surface the new "running" status.
      window.setTimeout(fetchStatus, 1500);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setTriggering(null);
    }
  };

  if (!status || !draft) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="h-4 w-4 text-primary" /> Auto-sync
          </CardTitle>
          <CardDescription>Cargando…</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-32 flex items-center justify-center text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      {/* Accent stripe — matches StatCard treatment */}
      <span
        aria-hidden
        className="block h-[3px] w-full"
        style={{
          background:
            "linear-gradient(90deg, hsl(var(--lima)) 0%, hsl(var(--primary)) 50%, hsl(var(--accent)) 100%)",
          opacity: draft.enabled ? 0.85 : 0.25,
        }}
      />
      <CardHeader className="pb-4">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div className="flex flex-col gap-1.5 min-w-0">
            <div className="flex items-center gap-2">
              <span className="eyebrow">YouTube · Background</span>
              <Badge variant={status.running ? "success" : "outline"} className="h-5 text-[10px]">
                {status.running ? "activo" : "detenido"}
              </Badge>
            </div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <RefreshCw className="h-4 w-4 text-primary" /> Auto-sync de YouTube
            </CardTitle>
            <CardDescription className="max-w-2xl">
              Tres niveles con intervalos independientes — más frecuente para
              datos ligeros, menos para sync completo.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <label
              htmlFor="autosync-master"
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 cursor-pointer transition-colors",
                "border border-border/70 bg-card",
                draft.enabled && "border-primary/40 bg-primary/5",
              )}
            >
              <div className="flex flex-col gap-0.5">
                <span className="font-mono text-[9px] uppercase text-muted-foreground">
                  Maestro
                </span>
                <span className={cn("text-[11px] font-medium", draft.enabled ? "text-primary" : "text-muted-foreground")}>
                  {draft.enabled ? "Encendido" : "Apagado"}
                </span>
              </div>
              <Switch
                id="autosync-master"
                checked={draft.enabled}
                onCheckedChange={(v) => patch("enabled", v)}
              />
            </label>
            <Button
              variant={isDirty ? "brand" : "outline"}
              size="sm"
              onClick={save}
              disabled={!isDirty || saving}
              className="gap-2"
            >
              {saving ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <CheckCircle2 className="h-3.5 w-3.5" />
              )}
              Guardar
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {!draft.enabled && (
          <div className="rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-warning flex items-center gap-2">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
            Auto-sync maestro desactivado — ningún tier va a correr aunque
            estén marcados abajo.
          </div>
        )}

        <div className="space-y-3">
          {TIERS.map((t) => (
            <TierCard
              key={t.id}
              def={t}
              tierState={status.tiers[t.id]}
              logs={status.logs[t.id] || []}
              draft={draft}
              masterEnabled={draft.enabled}
              onPatch={patch}
              onTrigger={() => triggerTier(t.id)}
              triggering={triggering === t.id}
            />
          ))}
        </div>

        {/* Recent-only extra setting: how many videos to refresh per channel. */}
        <div className="rounded-lg border border-border/40 bg-muted/10 p-4 flex items-start gap-3">
          <div className="rounded-md bg-primary/10 text-primary p-2 shrink-0">
            <Eye className="h-4 w-4" />
          </div>
          <div className="flex-1 space-y-2">
            <div className="flex items-baseline justify-between gap-2 flex-wrap">
              <div className="flex flex-col">
                <span className="font-mono text-[9px] uppercase text-muted-foreground">
                  Tier Recent · Fine-tune
                </span>
                <Label className="text-[13px] font-medium">
                  Videos por canal a refrescar
                </Label>
              </div>
              <Input
                type="number"
                min={1}
                max={50}
                value={draft.recent_video_count}
                onChange={(e) =>
                  patch("recent_video_count", clamp(parseInt(e.target.value || "10", 10), 1, 50))
                }
                className="w-20 h-8 text-xs tabular-nums"
              />
            </div>
            <p className="text-xs text-muted-foreground">
              Refresca solo los <b className="text-foreground">{draft.recent_video_count}</b> más
              recientes. Bajalo si tienes muchos canales para evitar rate-limits.
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function TierCard({
  def,
  tierState,
  logs,
  draft,
  masterEnabled,
  onPatch,
  onTrigger,
  triggering,
}: {
  def: TierDef;
  tierState?: AutoSyncTierState;
  logs: string[];
  draft: AutoSyncConfig;
  masterEnabled: boolean;
  onPatch: (k: keyof AutoSyncConfig, v: AutoSyncConfig[keyof AutoSyncConfig]) => void;
  onTrigger: () => void;
  triggering: boolean;
}) {
  const enabled = Boolean(draft[def.enabledKey]);
  const interval = Number(draft[def.intervalKey]);
  const Icon = def.icon;

  const effective = masterEnabled && enabled;
  const status = tierState?.last_status;

  return (
    <div
      className={cn(
        "relative rounded-lg border bg-card overflow-hidden transition-all",
        effective ? "border-border/60" : "border-border/30 opacity-70",
      )}
    >
      {/* Left accent rail — visible only when tier is effective */}
      <span
        aria-hidden
        className="absolute left-0 top-0 bottom-0 w-[3px] transition-opacity"
        style={{
          background: `hsl(var(--${def.accent}))`,
          opacity: effective ? 0.9 : 0.15,
        }}
      />

      <div className="pl-4 pr-3 py-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className={cn("rounded-md p-2 shrink-0 transition-colors")}
              style={{
                background: effective
                  ? `hsl(var(--${def.accent}) / 0.14)`
                  : "hsl(var(--muted))",
                color: effective ? `hsl(var(--${def.accent}))` : "hsl(var(--muted-foreground))",
              }}
            >
              <Icon className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span
                  className="font-mono text-[9px] uppercase"
                  style={{ color: effective ? `hsl(var(--${def.accent}))` : "hsl(var(--muted-foreground))" }}
                >
                  {def.eyebrow}
                </span>
                <TierStatusPill status={status} />
              </div>
              <div className="font-medium text-[13.5px] mt-0.5">{def.label}</div>
              <div className="text-[11.5px] text-muted-foreground mt-0.5">{def.description}</div>
            </div>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-1.5 rounded-md border border-border/50 bg-background/40 px-2.5 py-1.5">
              <Label className="text-[10px] uppercase text-muted-foreground font-mono">
                cada
              </Label>
              <Input
                type="number"
                min={def.minInterval}
                max={def.maxInterval}
                value={interval}
                onChange={(e) =>
                  onPatch(
                    def.intervalKey,
                    clamp(
                      parseInt(e.target.value || String(def.minInterval), 10),
                      def.minInterval,
                      def.maxInterval,
                    ),
                  )
                }
                className="w-14 h-6 text-xs tabular-nums border-0 bg-transparent px-1 focus-visible:ring-0"
              />
              <span className="text-[10px] text-muted-foreground font-mono">{def.intervalUnit}</span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="gap-1.5 h-8"
              onClick={onTrigger}
              disabled={triggering || !effective}
              title={effective ? "Forzar ejecución inmediata" : "Activa el tier primero"}
            >
              {triggering ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <PlayCircle className="h-3.5 w-3.5" />
              )}
              Ahora
            </Button>
            <Switch checked={enabled} onCheckedChange={(v) => onPatch(def.enabledKey, v)} />
          </div>
        </div>

        {effective && (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-2">
            <Stat
              label="Última"
              value={tierState?.last_run_at ? relativeTime(tierState.last_run_at) : "—"}
              hint={tierState?.last_run_at}
              accent={def.accent}
            />
            <Stat
              label="Próxima"
              value={tierState?.next_run_at ? relativeFuture(tierState.next_run_at) : "—"}
              hint={tierState?.next_run_at}
              accent={def.accent}
            />
            <Stat
              label="Estado"
              value={tierState?.last_message || (status === "ok" ? "OK" : status === "error" ? "Error" : "—")}
              highlight={status === "error"}
              accent={def.accent}
            />
          </div>
        )}

        {(tierState?.consecutive_failures || 0) >= 2 && (
          <div className="mt-2 text-[11px] text-warning flex items-center gap-1.5">
            <AlertCircle className="h-3 w-3" />
            {tierState?.consecutive_failures} fallos consecutivos — intervalo en backoff exponencial.
          </div>
        )}

        {logs.length > 0 && effective && (
          <details className="mt-2 text-xs group/logs">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground flex items-center gap-1.5 select-none">
              <span className="font-mono text-[10px] uppercase">Logs recientes</span>
              <Badge variant="outline" className="h-4 text-[9px] px-1.5">{logs.length}</Badge>
            </summary>
            <div className="mt-2 font-mono text-[11px] bg-background/60 text-foreground/80 rounded-md border border-border/40 p-2 max-h-32 overflow-auto scrollbar-thin">
              {logs.slice(-20).map((l, i) => (
                <div key={i} className="whitespace-pre-wrap break-words leading-relaxed">
                  {l}
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}

function TierStatusPill({ status }: { status?: string }) {
  if (status === "running") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-mono uppercase text-primary">
        <Loader2 className="h-2.5 w-2.5 animate-spin" /> corriendo
      </span>
    );
  }
  if (status === "ok") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-mono uppercase text-success">
        <CheckCircle2 className="h-2.5 w-2.5" /> ok
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-mono uppercase text-destructive">
        <AlertCircle className="h-2.5 w-2.5" /> error
      </span>
    );
  }
  if (status === "disabled") {
    return (
      <span className="text-[10px] font-mono uppercase text-muted-foreground">
        desactivado
      </span>
    );
  }
  return null;
}

function Stat({
  label,
  value,
  hint,
  highlight,
  accent,
}: {
  label: string;
  value: string;
  hint?: string;
  highlight?: boolean;
  accent?: TierAccent;
}) {
  return (
    <div
      className="rounded-md border border-border/40 bg-background/40 px-2.5 py-1.5 transition-colors hover:bg-background/60"
      title={hint}
    >
      <div
        className="flex items-center gap-1 text-[9px] uppercase font-mono"
        style={{
          color: accent ? `hsl(var(--${accent}))` : "hsl(var(--muted-foreground))",
          opacity: 0.85,
        }}
      >
        <Clock className="h-3 w-3" />
        {label}
      </div>
      <div
        className={cn(
          "text-xs font-medium mt-0.5 truncate tabular-nums",
          highlight && "text-destructive",
        )}
      >
        {value}
      </div>
    </div>
  );
}

// Helpers ------------------------------------------------------------------

function clamp(n: number, min: number, max: number): number {
  if (!Number.isFinite(n)) return min;
  return Math.max(min, Math.min(max, n));
}

function relativeFuture(value?: string): string {
  if (!value) return "—";
  const d = new Date(value);
  if (isNaN(d.getTime())) return value;
  const diff = d.getTime() - Date.now();
  // Past or right-now — server-side delay between writing next_run_at and the
  // wakeup itself can put us a couple of seconds past it. Show "ahora" instead
  // of a misleading "hace unos segundos".
  if (diff <= 5_000) return "ahora";
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `en ${sec}s`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `en ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `en ${h}h ${min % 60}min`;
  const days = Math.floor(h / 24);
  return `en ${days}d`;
}
