import { useEffect, useRef, useState } from "react";
import {
  HardDrive,
  DollarSign,
  AlertTriangle,
  ListChecks,
  Bell,
  Archive,
  Trash2,
  RefreshCw,
  Eraser,
  Send,
  Download,
  Upload,
  ImageIcon,
  FileText,
  Search,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";

import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { EmptyState } from "@/components/ui/empty-state";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/ConfirmDialog";

import {
  api,
  type DiskUsage,
  type CostSummary,
  type ErrorList,
  type JobLogEntry,
  type NotifSettings,
} from "@/lib/api";
import { formatBytes, relativeTime, formatDate, truncate } from "@/lib/utils";

export function Operations() {
  return (
    <>
      <Header
        eyebrow="Operaciones"
        title="Observabilidad y mantenimiento"
        description="Disco, costos, errores, historial, notificaciones y backup."
      />
      <PageShell>
        <Tabs defaultValue="disk" className="w-full">
          <TabsList className="flex flex-wrap h-auto gap-1">
            <TabsTrigger value="disk" className="gap-2">
              <HardDrive className="h-4 w-4" /> Disco
            </TabsTrigger>
            <TabsTrigger value="cost" className="gap-2">
              <DollarSign className="h-4 w-4" /> Costos
            </TabsTrigger>
            <TabsTrigger value="errors" className="gap-2">
              <AlertTriangle className="h-4 w-4" /> Errores
            </TabsTrigger>
            <TabsTrigger value="logs" className="gap-2">
              <ListChecks className="h-4 w-4" /> Historial
            </TabsTrigger>
            <TabsTrigger value="notifications" className="gap-2">
              <Bell className="h-4 w-4" /> Notificaciones
            </TabsTrigger>
            <TabsTrigger value="backup" className="gap-2">
              <Archive className="h-4 w-4" /> Backup
            </TabsTrigger>
          </TabsList>

          <TabsContent value="disk"><DiskTab /></TabsContent>
          <TabsContent value="cost"><CostTab /></TabsContent>
          <TabsContent value="errors"><ErrorsTab /></TabsContent>
          <TabsContent value="logs"><LogsTab /></TabsContent>
          <TabsContent value="notifications"><NotificationsTab /></TabsContent>
          <TabsContent value="backup"><BackupTab /></TabsContent>
        </Tabs>
      </PageShell>
    </>
  );
}

// ---------------------------------------------------------------------------
// Disk
// ---------------------------------------------------------------------------

function DiskTab() {
  const [data, setData] = useState<DiskUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmClear, setConfirmClear] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setData(await api.opsDisk());
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const onClearTemp = async () => {
    setConfirmClear(false);
    try {
      const r = await api.opsClearTemp();
      toast.success(`${r.deleted} archivos · ${formatBytes(r.bytes_freed)} liberados`);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  if (loading && !data) return <Skeleton className="h-96 w-full" />;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="Total .mp/" value={formatBytes(data.total_bytes)} sub={`${data.files} archivos`} />
        <StatTile label="Libre en disco" value={data.disk_free_bytes >= 0 ? formatBytes(data.disk_free_bytes) : "—"} />
        <StatTile label="Tipos" value={String(data.by_ext.length)} sub="extensiones" />
        <StatTile
          label="Más antiguo"
          value={data.oldest ? relativeTime(new Date(data.oldest.mtime * 1000).toISOString()) : "—"}
          sub={data.oldest ? truncate(data.oldest.path, 30) : undefined}
        />
      </div>

      <div className="flex gap-2">
        <Button onClick={load} variant="outline" size="sm" className="gap-2">
          <RefreshCw className="h-4 w-4" /> Refrescar
        </Button>
        <Button onClick={() => setConfirmClear(true)} variant="outline" size="sm" className="gap-2">
          <Eraser className="h-4 w-4" /> Borrar scratch (.wav/.png/.srt)
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle className="text-base">Por extensión</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-1.5">
              {data.by_ext.map((row) => {
                const pct = data.total_bytes ? (row.bytes / data.total_bytes) * 100 : 0;
                return (
                  <div key={row.ext}>
                    <div className="flex justify-between text-xs">
                      <span className="font-mono">{row.ext}</span>
                      <span className="text-muted-foreground">{formatBytes(row.bytes)} · {row.count}</span>
                    </div>
                    <div className="h-1.5 bg-muted/60 rounded-full overflow-hidden">
                      <div className="h-full bg-primary rounded-full" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
              {data.by_ext.length === 0 && <EmptyState title="Vacío" description="No hay archivos en .mp/" />}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Top 25 archivos</CardTitle></CardHeader>
          <CardContent>
            <div className="text-xs space-y-1 max-h-[420px] overflow-y-auto">
              {data.biggest.map((f) => (
                <div key={f.path} className="flex justify-between gap-3 py-1 border-b border-border/40 last:border-0">
                  <span className="font-mono truncate" title={f.path}>{f.path}</span>
                  <span className="text-muted-foreground shrink-0">{formatBytes(f.bytes)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <ConfirmDialog
        open={confirmClear}
        onOpenChange={setConfirmClear}
        title="Borrar archivos scratch"
        description="Elimina .wav, .png, .srt y .jpg de la raíz de .mp/. Los .mp4 y JSONs de estado se mantienen."
        confirmLabel="Borrar"
        onConfirm={onClearTemp}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cost
// ---------------------------------------------------------------------------

function CostTab() {
  const [data, setData] = useState<CostSummary | null>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [confirmReset, setConfirmReset] = useState(false);

  const load = async () => {
    setLoading(true);
    try { setData(await api.opsCost(days)); }
    catch (e) { toast.error((e as Error).message); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [days]);

  const reset = async () => {
    setConfirmReset(false);
    try {
      await api.opsResetCost();
      toast.success("Log de costos vaciado");
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  if (loading && !data) return <Skeleton className="h-96 w-full" />;
  if (!data) return null;

  const maxDay = Math.max(0, ...data.by_day.map((d) => d.cost_usd));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatTile label={`Total ${days}d`} value={`$${data.total_usd.toFixed(4)}`} />
        <StatTile label="Llamadas" value={String(data.total_calls)} />
        <StatTile label="Proveedores" value={String(data.by_provider.length)} />
        <StatTile label="Modelos" value={String(data.by_model.length)} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Select value={String(days)} onValueChange={(v) => setDays(parseInt(v, 10))}>
          <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="1">1 día</SelectItem>
            <SelectItem value="7">7 días</SelectItem>
            <SelectItem value="30">30 días</SelectItem>
            <SelectItem value="90">90 días</SelectItem>
            <SelectItem value="365">1 año</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={load} className="gap-2">
          <RefreshCw className="h-4 w-4" /> Refrescar
        </Button>
        <Button variant="outline" size="sm" onClick={() => setConfirmReset(true)} className="gap-2">
          <Trash2 className="h-4 w-4" /> Resetear log
        </Button>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Costo por día</CardTitle></CardHeader>
        <CardContent>
          {data.by_day.length === 0 ? (
            <EmptyState
              title="Sin datos todavía"
              description="No hay llamadas registradas en este rango. Las llamadas a Gemini se loguean automáticamente."
            />
          ) : (
            <div className="flex items-end gap-1 h-40">
              {data.by_day.map((d) => {
                const h = maxDay > 0 ? (d.cost_usd / maxDay) * 100 : 0;
                return (
                  <div key={d.day} className="flex-1 flex flex-col items-center gap-1 group" title={`${d.day} · $${d.cost_usd.toFixed(4)} · ${d.calls} llamadas`}>
                    <div className="w-full bg-primary/70 hover:bg-primary rounded-t" style={{ height: `${h}%`, minHeight: 2 }} />
                    <span className="text-[9px] text-muted-foreground rotate-45 origin-left whitespace-nowrap mt-3">{d.day.slice(5)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle className="text-base">Por proveedor</CardTitle></CardHeader>
          <CardContent>
            <BucketList rows={data.by_provider.map((b) => ({ key: b.provider!, ...b }))} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Por modelo</CardTitle></CardHeader>
          <CardContent>
            <BucketList rows={data.by_model.map((b) => ({ key: b.model!, ...b }))} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Últimas 50 llamadas</CardTitle></CardHeader>
        <CardContent>
          <div className="text-xs max-h-[360px] overflow-y-auto">
            {data.recent.length === 0 ? (
              <span className="text-muted-foreground">Sin actividad reciente.</span>
            ) : (
              <table className="w-full">
                <thead className="text-muted-foreground sticky top-0 bg-background">
                  <tr>
                    <th className="text-left py-1">Hora</th>
                    <th className="text-left py-1">Proveedor</th>
                    <th className="text-left py-1">Modelo</th>
                    <th className="text-right py-1">In/Out</th>
                    <th className="text-right py-1">USD</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent.map((e, i) => (
                    <tr key={i} className="border-t border-border/40">
                      <td className="py-1 font-mono">{new Date(e.ts * 1000).toLocaleTimeString()}</td>
                      <td className="py-1">{e.provider}</td>
                      <td className="py-1 font-mono truncate max-w-[200px]">{e.model}</td>
                      <td className="py-1 text-right text-muted-foreground">{e.in_tokens}/{e.out_tokens}</td>
                      <td className="py-1 text-right font-mono">${e.cost_usd.toFixed(5)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmReset}
        onOpenChange={setConfirmReset}
        title="Resetear log de costos"
        description="Elimina todo el historial de llamadas. Esta acción no se puede deshacer."
        confirmLabel="Resetear"
        onConfirm={reset}
      />
    </div>
  );
}

function BucketList({ rows }: { rows: Array<{ key: string; cost_usd: number; calls: number }> }) {
  if (rows.length === 0) return <span className="text-xs text-muted-foreground">Sin datos.</span>;
  const total = rows.reduce((s, r) => s + r.cost_usd, 0) || 1;
  return (
    <div className="space-y-1.5">
      {rows.map((r) => {
        const pct = (r.cost_usd / total) * 100;
        return (
          <div key={r.key}>
            <div className="flex justify-between text-xs">
              <span className="font-mono truncate max-w-[200px]">{r.key}</span>
              <span className="text-muted-foreground">${r.cost_usd.toFixed(4)} · {r.calls}</span>
            </div>
            <div className="h-1.5 bg-muted/60 rounded-full overflow-hidden">
              <div className="h-full bg-primary rounded-full" style={{ width: `${pct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Errors (upload_failures)
// ---------------------------------------------------------------------------

function ErrorsTab() {
  const [data, setData] = useState<ErrorList | null>(null);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<{ name: string; file: string } | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try { setData(await api.opsErrors()); }
    catch (e) { toast.error((e as Error).message); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const onDelete = async () => {
    if (!deleting) return;
    try {
      await api.opsDeleteError(deleting);
      toast.success("Carpeta eliminada");
      setDeleting(null);
      load();
    } catch (e) { toast.error((e as Error).message); }
  };

  const onClearAll = async () => {
    setConfirmClear(false);
    try {
      const r = await api.opsClearErrors();
      toast.success(`${r.deleted} carpetas eliminadas`);
      load();
    } catch (e) { toast.error((e as Error).message); }
  };

  if (loading && !data) return <Skeleton className="h-96 w-full" />;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="text-sm">{data.total} fallos registrados</Badge>
        <Button variant="outline" size="sm" onClick={load} className="gap-2"><RefreshCw className="h-4 w-4" /> Refrescar</Button>
        {data.total > 0 && (
          <Button variant="outline" size="sm" onClick={() => setConfirmClear(true)} className="gap-2">
            <Trash2 className="h-4 w-4" /> Limpiar todo
          </Button>
        )}
      </div>

      {data.by_tag.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Tipos de error</CardTitle></CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {data.by_tag.map((t) => (
                <Badge key={t.tag} variant="secondary" className="gap-1">
                  <span className="font-mono">{t.tag}</span>
                  <span className="opacity-70">×{t.count}</span>
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {data.items.length === 0 ? (
        <EmptyState title="Sin errores" description="No hay carpetas en .mp/upload_failures/." />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {data.items.map((it) => {
            const screenshot = it.files.find((f) => f.name.toLowerCase().endsWith(".png"));
            const html = it.files.find((f) => f.name.toLowerCase().endsWith(".html"));
            return (
              <Card key={it.name}>
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <CardTitle className="text-sm font-mono truncate">{it.tag}</CardTitle>
                      <div className="text-xs text-muted-foreground mt-1">
                        {relativeTime(new Date(it.ts * 1000).toISOString())} · {formatBytes(it.size_bytes)}
                      </div>
                    </div>
                    <Button variant="ghost" size="icon" onClick={() => setDeleting(it.name)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2">
                  {screenshot && (
                    <button
                      onClick={() => setPreview({ name: it.name, file: screenshot.name })}
                      className="block w-full overflow-hidden rounded border border-border/60 hover:border-primary"
                    >
                      <img
                        src={api.opsErrorFileUrl(it.name, screenshot.name)}
                        alt="screenshot"
                        className="w-full h-32 object-cover"
                      />
                    </button>
                  )}
                  {it.context && (
                    <pre className="text-[11px] bg-muted/40 rounded p-2 max-h-24 overflow-y-auto whitespace-pre-wrap">{it.context}</pre>
                  )}
                  <div className="flex flex-wrap gap-1">
                    {screenshot && (
                      <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7"
                              onClick={() => setPreview({ name: it.name, file: screenshot.name })}>
                        <ImageIcon className="h-3 w-3" /> Screenshot
                      </Button>
                    )}
                    {html && (
                      <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7" asChild>
                        <a href={api.opsErrorFileUrl(it.name, html.name)} target="_blank" rel="noreferrer">
                          <FileText className="h-3 w-3" /> HTML
                        </a>
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <Dialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)}>
        <DialogContent className="max-w-4xl">
          <DialogHeader><DialogTitle className="font-mono text-sm">{preview?.name}</DialogTitle></DialogHeader>
          {preview && (
            <img src={api.opsErrorFileUrl(preview.name, preview.file)} alt="preview" className="w-full rounded" />
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Eliminar fallo"
        description="Borra la carpeta y todos sus archivos (screenshot, html, context)."
        confirmLabel="Eliminar"
        onConfirm={onDelete}
      />
      <ConfirmDialog
        open={confirmClear}
        onOpenChange={setConfirmClear}
        title="Limpiar todos los fallos"
        description={`Esto elimina las ${data.total} carpetas de upload_failures.`}
        confirmLabel="Limpiar todo"
        onConfirm={onClearAll}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Logs (job history)
// ---------------------------------------------------------------------------

function LogsTab() {
  const [items, setItems] = useState<JobLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<string>("");
  const [detail, setDetail] = useState<{ id: string; content: string } | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const debounce = useRef<number | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.opsJobLog({ q, status, limit: 200 });
      setItems(r.items);
      setTotal(r.total);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (debounce.current) window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(load, 250);
    return () => { if (debounce.current) window.clearTimeout(debounce.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, status]);

  const showDetail = async (id: string) => {
    try {
      const r = await api.opsJobLogDetail(id);
      setDetail({ id, content: r.content });
    } catch (e) {
      toast.error("No hay log persistido para ese job");
    }
  };

  const clearAll = async () => {
    setConfirmClear(false);
    try { await api.opsClearJobLog(); toast.success("Historial vaciado"); load(); }
    catch (e) { toast.error((e as Error).message); }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative flex-1 min-w-[220px] max-w-md">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar título o última línea..." className="pl-8" />
        </div>
        <Select value={status || "all"} onValueChange={(v) => setStatus(v === "all" ? "" : v)}>
          <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos</SelectItem>
            <SelectItem value="done">Done</SelectItem>
            <SelectItem value="error">Error</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={load} className="gap-2"><RefreshCw className="h-4 w-4" /> Refrescar</Button>
        <Button variant="outline" size="sm" onClick={() => setConfirmClear(true)} className="gap-2"><Trash2 className="h-4 w-4" /> Vaciar</Button>
        <Badge variant="outline">{total} jobs</Badge>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : items.length === 0 ? (
        <EmptyState title="Sin historial" description="Los jobs terminados se guardan acá automáticamente." />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="max-h-[600px] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="text-muted-foreground sticky top-0 bg-background border-b border-border/70">
                  <tr>
                    <th className="text-left py-2 px-3">Título</th>
                    <th className="text-left py-2 px-3">Estado</th>
                    <th className="text-left py-2 px-3">Inicio</th>
                    <th className="text-right py-2 px-3">Duración</th>
                    <th className="text-left py-2 px-3">Última línea</th>
                    <th className="py-2 px-3"></th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((j) => (
                    <tr key={j.id} className="border-b border-border/40 hover:bg-muted/30">
                      <td className="py-1.5 px-3 font-medium truncate max-w-[200px]">{j.title}</td>
                      <td className="py-1.5 px-3">
                        <Badge variant={j.status === "done" ? "success" : j.status === "error" ? "destructive" : "outline"}>
                          {j.status}
                        </Badge>
                      </td>
                      <td className="py-1.5 px-3 text-muted-foreground">{relativeTime(j.started_at)}</td>
                      <td className="py-1.5 px-3 text-right font-mono">{j.elapsed.toFixed(1)}s</td>
                      <td className="py-1.5 px-3 truncate max-w-[280px] font-mono text-[11px] text-muted-foreground" title={j.last_line}>
                        {truncate(j.last_line, 80)}
                      </td>
                      <td className="py-1.5 px-3 text-right">
                        <Button size="sm" variant="ghost" onClick={() => showDetail(j.id)}>
                          Ver log
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-w-4xl">
          <DialogHeader><DialogTitle className="font-mono text-sm">{detail?.id}</DialogTitle></DialogHeader>
          <pre className="text-[11px] bg-muted/40 rounded p-3 max-h-[60vh] overflow-y-auto whitespace-pre-wrap font-mono">{detail?.content}</pre>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirmClear}
        onOpenChange={setConfirmClear}
        title="Vaciar historial"
        description="Borra el log persistido y los archivos detallados de cada job."
        confirmLabel="Vaciar"
        onConfirm={clearAll}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

function NotificationsTab() {
  const [s, setS] = useState<NotifSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    api.opsGetNotifications()
      .then(setS)
      .catch((e) => toast.error((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    if (!s) return;
    setSaving(true);
    try {
      await api.opsPutNotifications(s);
      toast.success("Configuración guardada");
    } catch (e) { toast.error((e as Error).message); }
    finally { setSaving(false); }
  };

  const test = async () => {
    setTesting(true);
    try {
      const r = await api.opsTestNotifications();
      const lines = Object.entries(r)
        .filter(([_, v]) => v)
        .map(([k, v]) => `${k}: ${v?.ok ? "OK" : "FAIL"}${v?.error ? ` (${v.error})` : ""}`);
      toast.success(lines.length ? lines.join(" · ") : "Sin webhooks configurados");
    } catch (e) { toast.error((e as Error).message); }
    finally { setTesting(false); }
  };

  if (loading || !s) return <Skeleton className="h-72 w-full" />;

  const upd = <K extends keyof NotifSettings>(k: K, v: NotifSettings[K]) =>
    setS({ ...s, [k]: v });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card>
        <CardHeader><CardTitle className="text-base">Discord</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div>
            <Label htmlFor="dwh">Webhook URL</Label>
            <Input id="dwh" value={s.discord_webhook_url}
                   onChange={(e) => upd("discord_webhook_url", e.target.value)}
                   placeholder="https://discord.com/api/webhooks/..." />
            <p className="text-xs text-muted-foreground mt-1">
              En Discord: Server Settings → Integrations → Webhooks → New Webhook → Copy URL.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Telegram</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div>
            <Label htmlFor="tbt">Bot token</Label>
            <Input id="tbt" type="password" value={s.telegram_bot_token}
                   onChange={(e) => upd("telegram_bot_token", e.target.value)}
                   placeholder="123456:ABC-DEF..." />
          </div>
          <div>
            <Label htmlFor="tcid">Chat ID</Label>
            <Input id="tcid" value={s.telegram_chat_id}
                   onChange={(e) => upd("telegram_chat_id", e.target.value)}
                   placeholder="-100123..." />
            <p className="text-xs text-muted-foreground mt-1">
              Habla con @BotFather para crear un bot, después agregalo a un chat y obtené el chat_id desde getUpdates.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card className="lg:col-span-2">
        <CardHeader><CardTitle className="text-base">Cuándo notificar</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">Job completado</div>
              <p className="text-xs text-muted-foreground">Ping en cada job que termina sin errores.</p>
            </div>
            <Switch checked={s.on_done} onCheckedChange={(v) => upd("on_done", v)} />
          </div>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">Job con error</div>
              <p className="text-xs text-muted-foreground">Ping en cada job que termina con código distinto de 0.</p>
            </div>
            <Switch checked={s.on_error} onCheckedChange={(v) => upd("on_error", v)} />
          </div>
          <div>
            <Label>Aviso de disco lleno (GB libres)</Label>
            <Input type="number" min={0} step={1}
                   value={s.disk_threshold_gb}
                   onChange={(e) => upd("disk_threshold_gb", parseFloat(e.target.value) || 0)} />
            <p className="text-xs text-muted-foreground mt-1">
              0 = desactivado. Si el disco baja de este valor, se notifica al final de cada job.
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="lg:col-span-2 flex gap-2">
        <Button onClick={save} disabled={saving} className="gap-2">
          {saving && <Loader2 className="h-4 w-4 animate-spin" />} Guardar
        </Button>
        <Button onClick={test} disabled={testing} variant="outline" className="gap-2">
          {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Enviar test
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Backup / restore
// ---------------------------------------------------------------------------

function BackupTab() {
  const [includeVideos, setIncludeVideos] = useState(false);
  const [wipe, setWipe] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const onRestore = async () => {
    if (!restoreFile) return;
    setRestoring(true);
    try {
      const r = await api.opsRestore(restoreFile, wipe);
      toast.success(`Restaurado: ${r.extracted} archivos · ${r.skipped} saltados${r.wiped ? " · estado previo borrado" : ""}`);
      setRestoreFile(null);
      if (fileRef.current) fileRef.current.value = "";
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setRestoring(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card>
        <CardHeader><CardTitle className="text-base">Crear backup</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-muted-foreground">
            Genera un .zip con <code>config.json</code> y el estado JSON de <code>.mp/</code> (cuentas, videos, productos, costos, historial).
          </p>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">Incluir archivos .mp4</div>
              <p className="text-xs text-muted-foreground">Puede agregar varios GB al backup.</p>
            </div>
            <Switch checked={includeVideos} onCheckedChange={setIncludeVideos} />
          </div>
          <Button asChild className="gap-2">
            <a href={api.opsBackupUrl(includeVideos)}>
              <Download className="h-4 w-4" /> Descargar backup
            </a>
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Restaurar</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-muted-foreground">
            Subí un .zip generado por esta misma página. Por defecto se hace merge sobre los archivos existentes.
          </p>
          <Input ref={fileRef} type="file" accept=".zip"
                 onChange={(e) => setRestoreFile(e.target.files?.[0] ?? null)} />
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">Borrar estado previo</div>
              <p className="text-xs text-muted-foreground">Elimina los .json de <code>.mp/</code> antes de extraer (los .mp4 se conservan).</p>
            </div>
            <Switch checked={wipe} onCheckedChange={setWipe} />
          </div>
          <Button onClick={onRestore} disabled={!restoreFile || restoring} className="gap-2">
            {restoring ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Restaurar
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="text-2xl font-semibold mt-1 truncate">{value}</div>
        {sub && <div className="text-xs text-muted-foreground mt-0.5 truncate">{sub}</div>}
      </CardContent>
    </Card>
  );
}
