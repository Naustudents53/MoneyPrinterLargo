import { useEffect, useState } from "react";
import { Trash2, Eraser, HardDrive, FileVideo } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { api, type Mp4FileEntry } from "@/lib/api";
import { toast } from "sonner";
import { formatDate, relativeTime } from "@/lib/utils";

export function Storage() {
  const [files, setFiles] = useState<Mp4FileEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [clearAll, setClearAll] = useState(false);

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
              <ul className="divide-y divide-border/60 rounded-lg border border-border/60 overflow-hidden">
                {files.map((f) => (
                  <li
                    key={f.name}
                    className="flex items-center gap-3 px-4 py-3 hover:bg-muted/30"
                  >
                    <div className="rounded-md bg-primary/10 p-2 text-primary">
                      <FileVideo className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-mono truncate">{f.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {relativeTime(f.mtime)} · {formatDate(f.mtime)}
                      </div>
                    </div>
                    <Badge variant="outline">{f.size_mb} MB</Badge>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setDeleting(f.name)}
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </li>
                ))}
              </ul>
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
    </>
  );
}
