import { useEffect, useState } from "react";
import {
  Trash2,
  Eraser,
  HardDrive,
  FileVideo,
  Play,
  CheckCircle2,
  CloudUpload,
  ExternalLink,
  CheckCheck,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { api, type Mp4FileEntry } from "@/lib/api";
import { toast } from "sonner";
import { formatDate, relativeTime } from "@/lib/utils";

export function Storage() {
  const [files, setFiles] = useState<Mp4FileEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [clearAll, setClearAll] = useState(false);
  const [previewing, setPreviewing] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      setFiles(await api.listMp4());
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const totalMb = files.reduce((s, f) => s + f.size_mb, 0);

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await api.deleteMp4(deleting);
      toast.success("Archivo eliminado");
      setDeleting(null);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const handleClearAll = async () => {
    try {
      const r = await api.clearMp4();
      toast.success(`${r.deleted} archivo(s) eliminado(s)`);
      setClearAll(false);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <>
      <Header
        title="Archivos de video"
        description="Limpia los .mp4 cacheados en .mp/ para liberar espacio."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => setClearAll(true)}
            disabled={files.length === 0}
            className="gap-2 text-destructive hover:text-destructive"
          >
            <Eraser className="h-4 w-4" /> Vaciar todo
          </Button>
        }
      />

      <PageShell>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HardDrive className="h-4 w-4 text-primary" />
              Total: {files.length} archivo(s) — {totalMb.toFixed(1)} MB
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-12" />
                ))}
              </div>
            ) : files.length === 0 ? (
              <EmptyState
                icon={FileVideo}
                title="Sin archivos cacheados"
                description="No hay .mp4 guardados en la carpeta .mp/."
              />
            ) : (
              (() => {
                const pending = files.filter((f) => !f.uploaded);
                const uploaded = files.filter((f) => f.uploaded);

                const renderRow = (f: Mp4FileEntry) => (
                  <li
                    key={f.name}
                    className="flex items-center gap-3 px-4 py-3 hover:bg-muted/30"
                  >
                    <div
                      className={
                        f.uploaded
                          ? "rounded-md bg-emerald-400/10 p-2 text-emerald-400"
                          : "rounded-md bg-amber-400/10 p-2 text-amber-400"
                      }
                    >
                      <FileVideo className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-mono truncate">{f.name}</div>
                      <div className="text-xs text-muted-foreground truncate">
                        {f.subject ? `${f.subject} · ` : ""}
                        {relativeTime(f.mtime)} · {formatDate(f.mtime)}
                      </div>
                    </div>
                    {f.uploaded ? (
                      <Badge variant="outline" className="gap-1 text-emerald-400 border-emerald-400/40 bg-emerald-400/10">
                        <CheckCircle2 className="h-3 w-3" /> Subido
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="gap-1 text-amber-400 border-amber-400/40 bg-amber-400/10">
                        <CloudUpload className="h-3 w-3" /> Listo para subir
                      </Badge>
                    )}
                    <Badge variant="outline">{f.size_mb} MB</Badge>
                    {f.uploaded && f.uploaded_url && (
                      <a href={f.uploaded_url} target="_blank" rel="noreferrer">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-muted-foreground hover:text-primary"
                          title="Abrir en YouTube"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </Button>
                      </a>
                    )}
                    {!f.uploaded && (
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={async () => {
                          try {
                            await api.markMp4Uploaded(f.name);
                            toast.success("Marcado como subido");
                            load();
                          } catch (e) {
                            toast.error((e as Error).message);
                          }
                        }}
                        className="text-muted-foreground hover:text-emerald-400"
                        title="Marcar como subido (cuando ya está en YouTube pero el sistema no lo detecta)"
                      >
                        <CheckCheck className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setPreviewing(f.name)}
                      className="text-muted-foreground hover:text-primary"
                      title="Reproducir"
                    >
                      <Play className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setDeleting(f.name)}
                      className="text-muted-foreground hover:text-destructive"
                      title="Eliminar"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </li>
                );

                const Section = ({
                  label,
                  count,
                  tone,
                  children,
                }: {
                  label: string;
                  count: number;
                  tone: "amber" | "emerald";
                  children: React.ReactNode;
                }) => (
                  <div className="rounded-lg border border-border/60 overflow-hidden">
                    <div
                      className={`px-4 py-2 text-xs uppercase tracking-wider font-semibold flex items-center gap-2 ${
                        tone === "amber"
                          ? "bg-amber-400/5 text-amber-300"
                          : "bg-emerald-400/5 text-emerald-300"
                      }`}
                    >
                      {tone === "amber" ? (
                        <CloudUpload className="h-3.5 w-3.5" />
                      ) : (
                        <CheckCircle2 className="h-3.5 w-3.5" />
                      )}
                      {label}
                      <span className="text-muted-foreground font-normal normal-case">
                        ({count})
                      </span>
                    </div>
                    <ul className="divide-y divide-border/60">{children}</ul>
                  </div>
                );

                return (
                  <div className="space-y-4">
                    {pending.length > 0 && (
                      <Section label="Listos para subir" count={pending.length} tone="amber">
                        {pending.map(renderRow)}
                      </Section>
                    )}
                    {uploaded.length > 0 && (
                      <Section label="Subidos a YouTube" count={uploaded.length} tone="emerald">
                        {uploaded.map(renderRow)}
                      </Section>
                    )}
                  </div>
                );
              })()
            )}
          </CardContent>
        </Card>
      </PageShell>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="¿Eliminar archivo?"
        description={deleting || ""}
        confirmLabel="Eliminar"
        variant="destructive"
        onConfirm={handleDelete}
      />

      <ConfirmDialog
        open={clearAll}
        onOpenChange={setClearAll}
        title="¿Vaciar todos los .mp4?"
        description={`Se eliminarán ${files.length} archivo(s) (${totalMb.toFixed(1)} MB).`}
        confirmLabel="Vaciar todo"
        variant="destructive"
        onConfirm={handleClearAll}
      />

      <Dialog open={!!previewing} onOpenChange={(o) => !o && setPreviewing(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="font-mono text-sm break-all">{previewing}</DialogTitle>
          </DialogHeader>
          {previewing && (
            <video
              controls
              autoPlay
              className="w-full rounded-md bg-black max-h-[70vh]"
              src={api.mp4RawUrl(previewing)}
            />
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setPreviewing(null)}>
              Cerrar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
