import { useEffect, useMemo, useState } from "react";
import {
  Save,
  Eye,
  Lock,
  Loader2,
  Settings as SettingsIcon,
  Sparkles,
  Image as ImageIcon,
  Mic,
  Twitter,
  Clock,
  RefreshCw,
  type LucideIcon,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type ConfigField } from "@/lib/api";
import { cn } from "@/lib/utils";
import { AutoSyncPanel } from "@/components/AutoSyncPanel";
import { toast } from "sonner";

// Map an API config group label to a design icon. Anything we don't know
// falls back to the generic settings cog so new groups still render.
const GROUP_ICONS: Record<string, LucideIcon> = {
  Core: SettingsIcon,
  LLM: Sparkles,
  Image: ImageIcon,
  Imagen: ImageIcon,
  Audio: Mic,
  Twitter: Twitter,
  Cron: Clock,
};

const GROUP_DESCRIPTIONS: Record<string, string> = {
  Core: "Workspace, scratch, defaults",
  LLM: "Provider, modelo, host",
  Image: "Backend, resolución, claves de API",
  Audio: "TTS, voces, transcripción",
  Twitter: "Idioma y comportamiento",
};

export function Settings() {
  const [fields, setFields] = useState<ConfigField[]>([]);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [original, setOriginal] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showSecrets, setShowSecrets] = useState(false);
  const [section, setSection] = useState<string>("");

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.getConfig();
      setFields(data.fields);
      setValues(data.raw);
      setOriginal(data.raw);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const grouped = useMemo(() => {
    const by: Record<string, ConfigField[]> = {};
    for (const f of fields) (by[f.group] ||= []).push(f);
    return by;
  }, [fields]);

  // Auto-select first section when fields arrive.
  useEffect(() => {
    if (!section && Object.keys(grouped).length) {
      setSection(Object.keys(grouped)[0]);
    }
  }, [grouped, section]);

  const dirty = useMemo(
    () => fields.some((f) => values[f.key] !== original[f.key]),
    [fields, values, original],
  );

  const setVal = (k: string, v: unknown) => setValues((p) => ({ ...p, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      const patch: Record<string, unknown> = {};
      for (const f of fields) {
        if (values[f.key] !== original[f.key]) patch[f.key] = values[f.key];
      }
      const res = await api.updateConfig(patch);
      setOriginal(res.raw);
      setValues(res.raw);
      toast.success("Configuración guardada");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const sections = Object.keys(grouped);
  const fieldCount = fields.length;
  const currentFields = grouped[section] || [];
  const currentDesc = GROUP_DESCRIPTIONS[section] || "";

  return (
    <>
      <Header
        eyebrow="· sistema"
        title="Configuración"
        description="config.json visual editor"
      />

      <PageShell>
        <section className="page-hero">
          <div className="page-hero-inner">
            <div>
              <span className="eyebrow block mb-2">config.json visual</span>
              <h1 className="page-title">
                Configuracion <span className="brand-text">sin miedo</span>
              </h1>
              <p className="page-subtitle">
                Editor por secciones para {fieldCount} campos del proyecto, con secretos
                protegidos y auto-sync en el mismo flujo.
              </p>
            </div>
            <div className="flex items-center gap-3 flex-wrap justify-end w-full sm:w-auto">
              <label className="command-strip flex h-10 items-center gap-2 rounded-xl px-3 text-[12.5px] text-muted-foreground cursor-pointer">
                <span>Mostrar secrets</span>
                <Switch checked={showSecrets} onCheckedChange={setShowSecrets} />
              </label>
              <Button
                variant="outline"
                size="sm"
                onClick={load}
                className="h-10 gap-2"
                disabled={loading}
              >
                <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
                Recargar
              </Button>
              <Button
                variant="brand"
                size="sm"
                onClick={save}
                disabled={!dirty || saving}
                className="h-10 gap-2"
              >
                {saving ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Save className="h-3.5 w-3.5" />
                )}
                Guardar cambios
              </Button>
            </div>
          </div>
        </section>

        {dirty && (
          <div className="command-strip rounded-xl px-4 py-3 text-[12.5px] flex items-center justify-between gap-3">
            <span>
              <span style={{ color: "hsl(var(--warning))" }}>●</span> Tienes cambios sin
              guardar.
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setValues(original)}
              className="h-7"
            >
              Descartar
            </Button>
          </div>
        )}

        {/* Auto-sync lives in its own dedicated panel because it has its
            own concept of "running" state and per-tier controls — wrapping
            it in the generic key/value editor below would lose half the UX. */}
        <AutoSyncPanel />

        {loading || !section ? (
          <Skeleton className="h-[540px]" />
        ) : (
          <div
            className="studio-surface overflow-hidden"
            style={{ background: "hsl(var(--card))" }}
          >
            <div
              className="grid grid-cols-1 xl:grid-cols-[260px_minmax(0,1fr)]"
              style={{ minHeight: 540 }}
            >
              {/* Left column — section nav */}
              <div
                className="px-2.5 py-3.5 flex flex-col gap-0.5 xl:sticky xl:top-0 xl:self-start"
                style={{
                  borderRight: "1px solid hsl(var(--border) / .07)",
                  borderBottom: "1px solid hsl(var(--border) / .07)",
                  background: "hsl(var(--bg-raised))",
                }}
              >
                {sections.map((s) => {
                  const active = s === section;
                  const Icon = GROUP_ICONS[s] || SettingsIcon;
                  return (
                    <button
                      key={s}
                      onClick={() => setSection(s)}
                      className={cn(
                        "group relative flex items-center gap-2.5 px-3 py-2.5 rounded-lg cursor-pointer text-left transition-colors",
                        active
                          ? "bg-surface text-foreground"
                          : "text-muted-foreground hover:bg-surface hover:text-foreground",
                      )}
                    >
                      {active && (
                        <span
                          aria-hidden
                          className="absolute left-[-10px] top-1.5 bottom-1.5 w-[3px] rounded-r bg-brand-gradient"
                          style={{
                            boxShadow: "0 0 12px hsl(var(--primary) / .55)",
                          }}
                        />
                      )}
                      <span
                        className="w-7 h-7 rounded-md flex items-center justify-center shrink-0"
                        style={{
                          background: active
                            ? "hsl(var(--primary) / .15)"
                            : "hsl(var(--background))",
                          border: `1px solid ${
                            active
                              ? "hsl(var(--primary) / .35)"
                              : "hsl(var(--border) / .07)"
                          }`,
                        }}
                      >
                        <Icon
                          className={cn(
                            "h-3.5 w-3.5",
                            active ? "text-primary" : "text-muted-foreground",
                          )}
                          strokeWidth={1.5}
                        />
                      </span>
                      <div className="flex-1 min-w-0">
                        <div
                          className={cn(
                            "text-[13px] truncate",
                            active ? "font-medium" : "font-normal",
                          )}
                        >
                          {s}
                        </div>
                        <div className="text-[11px] text-muted-foreground truncate mt-px">
                          {GROUP_DESCRIPTIONS[s] || `${grouped[s].length} campos`}
                        </div>
                      </div>
                      <span
                        className="font-mono px-1.5 py-px rounded text-[9.5px]"
                        style={{
                          border: "1px solid hsl(var(--border) / .12)",
                          color: "hsl(var(--muted-foreground))",
                        }}
                      >
                        {grouped[s].length}
                      </span>
                    </button>
                  );
                })}
              </div>

              {/* Right column — field editor */}
              <div className="px-4 py-5 sm:px-7 sm:py-6">
                <div className="mb-[18px] flex items-center gap-2.5 flex-wrap">
                  <span className="eyebrow">· {section.toLowerCase()}</span>
                  <span className="font-display text-[18px] font-semibold text-foreground">
                    {section}
                  </span>
                  {currentDesc && (
                    <span className="text-[12px] text-muted-foreground">
                      {currentDesc}
                    </span>
                  )}
                </div>
                {currentFields.map((f) => (
                  <ConfigFieldRow
                    key={f.key}
                    field={f}
                    value={values[f.key]}
                    onChange={(v) => setVal(f.key, v)}
                    showSecrets={showSecrets}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
      </PageShell>
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ConfigFieldRow — 200px label / value, hairline divider beneath each row.
// ─────────────────────────────────────────────────────────────────────────────
function ConfigFieldRow({
  field,
  value,
  onChange,
  showSecrets,
}: {
  field: ConfigField;
  value: unknown;
  onChange: (v: unknown) => void;
  showSecrets: boolean;
}) {
  if (field.type === "bool") {
    return (
      <div
        className="flex items-start justify-between gap-3.5 py-3"
        style={{ borderBottom: "1px solid hsl(var(--border) / .04)" }}
      >
        <div className="flex-1 min-w-0">
          <div className="text-[13px] text-foreground font-medium">{field.label}</div>
          <div className="text-[11.5px] text-muted-foreground mt-0.5 font-mono">
            {field.key}
          </div>
        </div>
        <Switch checked={Boolean(value)} onCheckedChange={onChange} />
      </div>
    );
  }

  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-[200px_minmax(0,1fr)] items-center gap-2 sm:gap-[18px] py-3"
      style={{
        borderBottom: "1px solid hsl(var(--border) / .04)",
      }}
    >
      <div>
        <div className="text-[13px] text-foreground font-medium">{field.label}</div>
        <div className="text-[11px] text-muted-foreground mt-0.5 font-mono truncate">
          {field.key}
        </div>
      </div>
      <div className="flex items-stretch gap-1.5 relative">
        {field.type === "int" ? (
          <ConfigInput
            type="number"
            value={String((value as number) ?? 0)}
            onChange={(v) => onChange(parseInt(v, 10) || 0)}
          />
        ) : field.type === "secret" ? (
          <>
            <ConfigInput
              type={showSecrets ? "text" : "password"}
              placeholder="(no configurado)"
              value={(value as string) ?? ""}
              onChange={onChange}
            />
            <button
              type="button"
              className="w-[34px] shrink-0 flex items-center justify-center rounded-lg text-muted-foreground hover:text-foreground transition-colors"
              style={{
                background: "hsl(var(--background))",
                border: "1px solid hsl(var(--border) / .07)",
              }}
              onClick={() => onChange(value)}
              aria-label={showSecrets ? "Ocultar" : "Mostrar"}
              tabIndex={-1}
            >
              {showSecrets ? <Eye className="h-3.5 w-3.5" /> : <Lock className="h-3.5 w-3.5" />}
            </button>
          </>
        ) : (
          <ConfigInput
            type="text"
            value={(value as string) ?? ""}
            onChange={onChange}
          />
        )}
      </div>
    </div>
  );
}

function ConfigInput({
  type,
  value,
  onChange,
  placeholder,
}: {
  type: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className="flex-1 h-[34px] px-3 rounded-lg outline-none text-foreground"
      style={{
        background: "hsl(var(--background))",
        border: "1px solid hsl(var(--border) / .07)",
        fontFamily: "'JetBrains Mono', ui-monospace, monospace",
        fontSize: 12,
        transition: "border-color 120ms ease",
      }}
      onFocus={(e) => (e.target.style.borderColor = "hsl(var(--primary) / .35)")}
      onBlur={(e) => (e.target.style.borderColor = "hsl(var(--border) / .07)")}
    />
  );
}
