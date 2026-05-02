import { useEffect, useMemo, useState } from "react";
import { Save, Eye, EyeOff, Settings as SettingsIcon, Loader2 } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { api, type ConfigField } from "@/lib/api";
import { toast } from "sonner";

export function Settings() {
  const [fields, setFields] = useState<ConfigField[]>([]);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [original, setOriginal] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showSecrets, setShowSecrets] = useState(false);

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
    for (const f of fields) {
      (by[f.group] ||= []).push(f);
    }
    return by;
  }, [fields]);

  const dirty = useMemo(() => {
    return fields.some((f) => values[f.key] !== original[f.key]);
  }, [fields, values, original]);

  const set = (k: string, v: unknown) => setValues((p) => ({ ...p, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      const patch: Record<string, unknown> = {};
      for (const f of fields) {
        if (values[f.key] !== original[f.key]) {
          patch[f.key] = values[f.key];
        }
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

  return (
    <>
      <Header
        title="Configuración"
        description="Edita config.json desde aquí — los cambios se aplican en cada nueva ejecución."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowSecrets((v) => !v)}
              className="gap-2"
            >
              {showSecrets ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              {showSecrets ? "Ocultar secrets" : "Mostrar secrets"}
            </Button>
            <Button
              variant="brand"
              size="sm"
              onClick={save}
              disabled={!dirty || saving}
              className="gap-2"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Guardar cambios
            </Button>
          </div>
        }
      />

      <PageShell>
        {dirty && (
          <div className="rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm flex items-center justify-between">
            <span className="text-warning-foreground">
              Tienes cambios sin guardar.
            </span>
            <Button size="sm" variant="ghost" onClick={() => setValues(original)}>
              Descartar
            </Button>
          </div>
        )}

        {loading ? (
          <div className="space-y-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-[200px]" />
            ))}
          </div>
        ) : (
          Object.entries(grouped).map(([group, items]) => (
            <Card key={group}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <SettingsIcon className="h-4 w-4 text-primary" />
                      {group}
                    </CardTitle>
                    <CardDescription>
                      {items.length} ajuste{items.length !== 1 ? "s" : ""}
                    </CardDescription>
                  </div>
                  <Badge variant="outline">{group}</Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {items.map((f) => (
                    <FieldRow
                      key={f.key}
                      field={f}
                      value={values[f.key]}
                      onChange={(v) => set(f.key, v)}
                      showSecrets={showSecrets}
                    />
                  ))}
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </PageShell>
    </>
  );
}

function FieldRow({
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
      <div className="flex items-center justify-between rounded-lg border border-border p-3">
        <div className="min-w-0 mr-3">
          <Label className="font-medium">{field.label}</Label>
          <p className="text-xs text-muted-foreground font-mono mt-0.5 truncate">{field.key}</p>
        </div>
        <Switch checked={Boolean(value)} onCheckedChange={onChange} />
      </div>
    );
  }
  if (field.type === "int") {
    return (
      <div className="space-y-1.5">
        <Label>
          {field.label}{" "}
          <span className="text-muted-foreground font-mono text-xs">{field.key}</span>
        </Label>
        <Input
          type="number"
          value={(value as number) ?? 0}
          onChange={(e) => onChange(parseInt(e.target.value, 10) || 0)}
        />
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      <Label>
        {field.label}{" "}
        <span className="text-muted-foreground font-mono text-xs">{field.key}</span>
      </Label>
      <Input
        type={field.type === "secret" && !showSecrets ? "password" : "text"}
        value={(value as string) ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={field.type === "secret" ? "(no configurado)" : ""}
        className={field.type === "secret" ? "font-mono" : ""}
      />
    </div>
  );
}
