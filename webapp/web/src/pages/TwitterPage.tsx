import { useEffect, useState } from "react";
import {
  Plus,
  Twitter,
  Pencil,
  Trash2,
  Send,
  MessageCircle,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ProgressDialog } from "@/components/ProgressDialog";
import { api, type TwitterAccount, type TwitterPost } from "@/lib/api";
import { toast } from "sonner";
import { formatDate, relativeTime, truncate } from "@/lib/utils";

export function TwitterPage() {
  const [accounts, setAccounts] = useState<TwitterAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<TwitterAccount | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<TwitterAccount | null>(null);
  const [postingFor, setPostingFor] = useState<string | null>(null);
  const [selected, setSelected] = useState<TwitterAccount | null>(null);
  const [posts, setPosts] = useState<TwitterPost[]>([]);
  const [postsLoading, setPostsLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.listTwitterAccounts();
      setAccounts(data);
      if (!selected && data.length > 0) setSelected(data[0]);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selected) return;
    setPostsLoading(true);
    api
      .listTwitterPosts(selected.id)
      .then(setPosts)
      .catch(() => {})
      .finally(() => setPostsLoading(false));
  }, [selected]);

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await api.deleteTwitterAccount(deleting.id);
      toast.success(`Cuenta "${deleting.nickname}" eliminada`);
      if (selected?.id === deleting.id) setSelected(null);
      setDeleting(null);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <>
      <Header
        title="Cuentas Twitter / X"
        description="Administra cuentas y postea tweets generados con IA."
        actions={
          <Button variant="brand" size="sm" className="gap-2" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" /> Nueva cuenta
          </Button>
        }
      />

      <PageShell>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1 space-y-3">
            {loading ? (
              <>
                {Array.from({ length: 2 }).map((_, i) => (
                  <Skeleton key={i} className="h-[110px]" />
                ))}
              </>
            ) : accounts.length === 0 ? (
              <EmptyState
                icon={Twitter}
                title="Sin cuentas Twitter"
                description="Crea una cuenta para empezar a postear."
                action={
                  <Button variant="brand" onClick={() => setCreating(true)}>
                    Crear cuenta
                  </Button>
                }
              />
            ) : (
              accounts.map((a) => (
                <button
                  key={a.id}
                  onClick={() => setSelected(a)}
                  className={`w-full text-left transition-all ${
                    selected?.id === a.id ? "ring-2 ring-primary" : ""
                  }`}
                >
                  <Card className="hover:border-primary/40">
                    <CardContent className="p-4 space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <div className="rounded-md bg-accent/15 p-1.5 text-accent shrink-0">
                            <Twitter className="h-4 w-4" />
                          </div>
                          <span className="font-semibold truncate">{a.nickname}</span>
                        </div>
                        <Badge variant="outline">{a.posts_count}</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground line-clamp-2">
                        {a.topic || "(sin tópico)"}
                      </p>
                      <div className="flex items-center justify-between pt-2 border-t border-border/60">
                        <Button
                          variant="brand"
                          size="sm"
                          className="gap-1.5 h-7"
                          onClick={(e) => {
                            e.stopPropagation();
                            setPostingFor(a.id);
                          }}
                        >
                          <Send className="h-3 w-3" /> Postear
                        </Button>
                        <div className="flex gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            onClick={(e) => {
                              e.stopPropagation();
                              setEditing(a);
                            }}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-muted-foreground hover:text-destructive"
                            onClick={(e) => {
                              e.stopPropagation();
                              setDeleting(a);
                            }}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </button>
              ))
            )}
          </div>

          <div className="lg:col-span-2">
            <Card>
              <CardContent className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="font-semibold flex items-center gap-2">
                      <MessageCircle className="h-4 w-4 text-accent" />
                      Posts {selected ? `· ${selected.nickname}` : ""}
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Historial de tweets registrados en el caché local.
                    </p>
                  </div>
                </div>

                {!selected ? (
                  <EmptyState title="Selecciona una cuenta" />
                ) : postsLoading ? (
                  <div className="space-y-2">
                    {Array.from({ length: 4 }).map((_, i) => (
                      <Skeleton key={i} className="h-16" />
                    ))}
                  </div>
                ) : posts.length === 0 ? (
                  <EmptyState
                    icon={MessageCircle}
                    title="Sin posts"
                    description="Esta cuenta no ha posteado todavía."
                  />
                ) : (
                  <ul className="space-y-2">
                    {posts.map((p) => (
                      <li
                        key={p.index}
                        className="rounded-lg border border-border/60 p-3 hover:bg-muted/30 transition-colors"
                      >
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                          <Badge variant="outline" className="text-[10px]">
                            #{p.index + 1}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {relativeTime(p.date)} · {formatDate(p.date)}
                          </span>
                        </div>
                        <p className="text-sm">{truncate(p.content, 280)}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </PageShell>

      <TwitterFormDialog
        open={creating}
        onOpenChange={setCreating}
        onSaved={() => {
          setCreating(false);
          load();
        }}
      />

      <TwitterFormDialog
        open={!!editing}
        onOpenChange={(o) => !o && setEditing(null)}
        account={editing ?? undefined}
        onSaved={() => {
          setEditing(null);
          load();
        }}
      />

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`¿Eliminar "${deleting?.nickname}"?`}
        description="Se borra del caché local. No afecta la cuenta real en x.com."
        variant="destructive"
        confirmLabel="Eliminar"
        onConfirm={handleDelete}
      />

      <ProgressDialog
        open={!!postingFor}
        onOpenChange={(o) => !o && setPostingFor(null)}
        title="Generando y posteando tweet"
        description="Selenium controla Firefox para postear en x.com."
        sseUrl={postingFor ? api.postTweetUrl(postingFor) : null}
        onDone={load}
      />
    </>
  );
}

function TwitterFormDialog({
  open,
  onOpenChange,
  account,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  account?: TwitterAccount;
  onSaved: () => void;
}) {
  const editing = !!account;
  const [data, setData] = useState({
    nickname: "",
    firefox_profile: "",
    topic: "",
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (account) {
      setData({
        nickname: account.nickname,
        firefox_profile: account.firefox_profile,
        topic: account.topic,
      });
    } else if (open) {
      setData({ nickname: "", firefox_profile: "", topic: "" });
    }
  }, [account, open]);

  const submit = async () => {
    if (!data.nickname.trim()) {
      toast.error("Nickname requerido");
      return;
    }
    setSaving(true);
    try {
      if (editing && account) {
        await api.updateTwitterAccount(account.id, data);
        toast.success("Cuenta actualizada");
      } else {
        await api.createTwitterAccount(data);
        toast.success("Cuenta creada");
      }
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing ? "Editar cuenta Twitter" : "Nueva cuenta Twitter"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Nickname *</Label>
            <Input
              value={data.nickname}
              onChange={(e) => setData((p) => ({ ...p, nickname: e.target.value }))}
              placeholder="Mi cuenta"
            />
          </div>
          <div className="space-y-2">
            <Label>Tema / niche</Label>
            <Input
              value={data.topic}
              onChange={(e) => setData((p) => ({ ...p, topic: e.target.value }))}
              placeholder="Tech, fitness, finanzas..."
            />
          </div>
          <div className="space-y-2">
            <Label>Path al perfil Firefox</Label>
            <Input
              value={data.firefox_profile}
              onChange={(e) => setData((p) => ({ ...p, firefox_profile: e.target.value }))}
              className="font-mono text-xs"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancelar
          </Button>
          <Button variant="brand" onClick={submit} disabled={saving}>
            {editing ? "Guardar" : "Crear"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
