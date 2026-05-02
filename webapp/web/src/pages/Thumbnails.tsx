import { useEffect, useState } from "react";
import {
  Image as ImageIcon,
  Trash2,
  Eraser,
  Download,
  Copy,
  Eye,
  Wand2,
  Sparkles,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { ProgressDialog } from "@/components/ProgressDialog";
import { api, type ThumbnailEntry } from "@/lib/api";
import { toast } from "sonner";
import { formatDate, relativeTime } from "@/lib/utils";

export function Thumbnails() {
  const [items, setItems] = useState<ThumbnailEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [topic, setTopic] = useState("");
  const [text, setText] = useState("");
  const [visual, setVisual] = useState("");
  const [progressOpen, setProgressOpen] = useState(false);
  const [sseUrl, setSseUrl] = useState<string | null>(null);

  const [previewing, setPreviewing] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [clearAll, setClearAll] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setItems(await api.listThumbnails());
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const totalKb = items.reduce((s, t) => s + t.size_kb, 0);

  const startGenerate = () => {
    if (!topic.trim() || !text.trim()) {
      toast.error("Tema y texto son obligatorios");
      return;
    }
    setSseUrl(api.thumbnailGenerateUrl({ topic: topic.trim(), text: text.trim(), visual: visual.trim() || undefined }));
    setProgressOpen(true);
  };

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await api.deleteThumbnail(deleting);
      toast.success("Thumbnail eliminado");
      setDeleting(null);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const handleClearAll = async () => {
    try {
      const r = await api.clearThumbnails();
      toast.success(`${r.deleted} thumbnail(s) eliminado(s)`);
      setClearAll(false);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const downloadOne = (name: string) => {
    const a = document.createElement("a");
    a.href = api.thumbnailRawUrl(name);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const copyOne = async (name: string) => {
    try {
      const res = await fetch(api.thumbnailRawUrl(name));
      const blob = await res.blob();
      // Browsers require image/png for ClipboardItem in most cases.
      const pngBlob =
        blob.type === "image/png"
          ? blob
          : await new Promise<Blob>((resolve, reject) => {
              const img = new Image();
              img.onload = () => {
                const c = document.createElement("canvas");
                c.width = img.naturalWidth;
                c.height = img.naturalHeight;
                const ctx = c.getContext("2d");
                if (!ctx) return reject(new Error("canvas ctx"));
                ctx.drawImage(img, 0, 0);
                c.toBlob((b) => (b ? resolve(b) : reject(new Error("toBlob"))), "image/png");
              };
              img.onerror = () => reject(new Error("img load"));
              img.src = URL.createObjectURL(blob);
            });
      await navigator.clipboard.write([
        new ClipboardItem({ "image/png": pngBlob }),
      ]);
      toast.success("Imagen copiada al portapapeles");
    } catch (e) {
      toast.error("No se pudo copiar: " + (e as Error).message);
    }
  };

  return (
    <>
      <Header
        title="Thumbnails"
        description="Genera, revisa y administra las miniaturas. Todas se guardan en thumbnails/."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => setClearAll(true)}
            disabled={items.length === 0}
            className="gap-2 text-destructive hover:text-destructive"
          >
            <Eraser className="h-4 w-4" /> Vaciar todo
          </Button>
        }
      />

      <PageShell>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Generator form */}
          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Wand2 className="h-5 w-5 text-primary" /> Crear thumbnail
              </CardTitle>
              <CardDescription>
                Leonardo XL para el fondo + overlay de texto. Tarda ~30–90s.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="topic">Tema del video</Label>
                <Input
                  id="topic"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="Ej: El colapso de civilizaciones antiguas"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="text">Texto overlay</Label>
                <Input
                  id="text"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="EL PATRON OCULTO"
                />
                <p className="text-[11px] text-muted-foreground">
                  Se convierte a mayúsculas. Máx ~3 líneas con auto-shrink.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="visual">
                  Prompt visual <span className="text-muted-foreground">(opcional)</span>
                </Label>
                <Textarea
                  id="visual"
                  rows={3}
                  value={visual}
                  onChange={(e) => setVisual(e.target.value)}
                  placeholder="Si lo dejas vacío, el LLM escribe uno desde el tema."
                />
              </div>
              <Button
                variant="brand"
                size="lg"
                onClick={startGenerate}
                disabled={!topic.trim() || !text.trim()}
                className="gap-2 w-full"
              >
                <Sparkles className="h-4 w-4" /> Generar thumbnail
              </Button>
            </CardContent>
          </Card>

          {/* Gallery */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ImageIcon className="h-4 w-4 text-primary" />
                Galería ({items.length})
                <Badge variant="outline" className="ml-2 font-mono">
                  {(totalKb / 1024).toFixed(1)} MB
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <Skeleton key={i} className="aspect-video" />
                  ))}
                </div>
              ) : items.length === 0 ? (
                <EmptyState
                  icon={ImageIcon}
                  title="Sin thumbnails"
                  description="Genera el primero con el formulario de la izquierda."
                />
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                  {items.map((t) => (
                    <ThumbCard
                      key={t.name}
                      item={t}
                      onPreview={() => setPreviewing(t.name)}
                      onDownload={() => downloadOne(t.name)}
                      onCopy={() => copyOne(t.name)}
                      onDelete={() => setDeleting(t.name)}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </PageShell>

      <ProgressDialog
        open={progressOpen}
        onOpenChange={(o) => {
          setProgressOpen(o);
          if (!o) load();
        }}
        title="Generando thumbnail"
        description="Leonardo XL + overlay Pillow."
        sseUrl={sseUrl}
      />

      <Dialog open={!!previewing} onOpenChange={(o) => !o && setPreviewing(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="font-mono text-sm break-all">{previewing}</DialogTitle>
            <DialogDescription>1280×720 — listo para YouTube.</DialogDescription>
          </DialogHeader>
          {previewing && (
            <img
              src={api.thumbnailRawUrl(previewing)}
              alt={previewing}
              className="w-full rounded-md bg-black/40"
            />
          )}
          <DialogFooter className="gap-2 flex-wrap">
            {previewing && (
              <>
                <Button variant="outline" onClick={() => copyOne(previewing)} className="gap-2">
                  <Copy className="h-4 w-4" /> Copiar
                </Button>
                <Button variant="outline" onClick={() => downloadOne(previewing)} className="gap-2">
                  <Download className="h-4 w-4" /> Descargar
                </Button>
              </>
            )}
            <Button variant="default" onClick={() => setPreviewing(null)}>
              Cerrar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="¿Eliminar thumbnail?"
        description={deleting || ""}
        confirmLabel="Eliminar"
        variant="destructive"
        onConfirm={handleDelete}
      />

      <ConfirmDialog
        open={clearAll}
        onOpenChange={setClearAll}
        title="¿Vaciar todos los thumbnails?"
        description={`Se eliminarán ${items.length} archivo(s).`}
        confirmLabel="Vaciar todo"
        variant="destructive"
        onConfirm={handleClearAll}
      />
    </>
  );
}

function ThumbCard({
  item,
  onPreview,
  onDownload,
  onCopy,
  onDelete,
}: {
  item: ThumbnailEntry;
  onPreview: () => void;
  onDownload: () => void;
  onCopy: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="group rounded-lg border border-border/60 overflow-hidden bg-card hover:border-primary/40 transition-colors">
      <button
        type="button"
        onClick={onPreview}
        className="block w-full aspect-video bg-black/40 overflow-hidden"
      >
        <img
          src={api.thumbnailRawUrl(item.name)}
          alt={item.name}
          loading="lazy"
          className="h-full w-full object-cover group-hover:scale-[1.02] transition-transform"
        />
      </button>
      <div className="p-3 space-y-2">
        <div className="text-xs font-mono truncate" title={item.name}>
          {item.name}
        </div>
        <div className="flex items-center justify-between text-[10px] text-muted-foreground">
          <span>{relativeTime(item.mtime)}</span>
          <span>{item.size_kb} KB · {formatDate(item.mtime)}</span>
        </div>
        <div className="flex items-center gap-1 pt-1">
          <Button variant="ghost" size="icon" onClick={onPreview} className="h-8 w-8" title="Ver">
            <Eye className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" onClick={onCopy} className="h-8 w-8" title="Copiar">
            <Copy className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" onClick={onDownload} className="h-8 w-8" title="Descargar">
            <Download className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onDelete}
            className="h-8 w-8 ml-auto text-muted-foreground hover:text-destructive"
            title="Eliminar"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
