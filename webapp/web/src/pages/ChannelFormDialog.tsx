import { useEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Loader2,
  Play,
  Square,
  Youtube,
  IdCard,
  Link2,
  AudioLines,
  Globe,
  AtSign,
  FolderOpen,
  Palette,
  Sparkles,
} from "lucide-react";
import { api, type Channel, type ChannelInput, type Voice } from "@/lib/api";
import { toast } from "sonner";

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  channel?: Channel;
  onSaved: () => void;
}

const HOOK_PROFILES = ["", "educational", "storytelling"];

export function ChannelFormDialog({ open, onOpenChange, channel, onSaved }: Props) {
  const editing = !!channel;
  const [saving, setSaving] = useState(false);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [data, setData] = useState<ChannelInput>({
    nickname: "",
    firefox_profile: "",
    niche: "",
    language: "español",
    image_style: "",
    short_voice: "",
    long_voice: "",
    hook_profile: "",
    voice_drama: false,
    youtube_handle: "",
  });

  useEffect(() => {
    if (!open) return;
    api
      .listVoices()
      .then((r) => setVoices(r.voices))
      .catch(() => setVoices([]));
  }, [open]);

  useEffect(() => {
    if (channel) {
      setData({
        nickname: channel.nickname,
        firefox_profile: channel.firefox_profile,
        niche: channel.niche,
        language: channel.language,
        image_style: channel.image_style,
        short_voice: channel.short_voice,
        long_voice: channel.long_voice,
        hook_profile: channel.hook_profile,
        voice_drama: channel.voice_drama,
        youtube_handle: channel.youtube_handle || "",
      });
    } else if (open) {
      setData({
        nickname: "",
        firefox_profile: "",
        niche: "",
        language: "español",
        image_style: "",
        short_voice: "",
        long_voice: "",
        hook_profile: "",
        voice_drama: false,
        youtube_handle: "",
      });
    }
  }, [channel, open]);

  const update = <K extends keyof ChannelInput>(k: K, v: ChannelInput[K]) =>
    setData((p) => ({ ...p, [k]: v }));

  const submit = async () => {
    if (!data.nickname.trim()) {
      toast.error("El nickname es obligatorio");
      return;
    }
    setSaving(true);
    try {
      if (editing && channel) {
        await api.updateChannel(channel.id, data);
        toast.success(`Canal "${data.nickname}" actualizado`);
      } else {
        await api.createChannel(data);
        toast.success(`Canal "${data.nickname}" creado`);
      }
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const initial = (data.nickname || "").trim().slice(0, 1).toUpperCase();
  const hasVoice = !!(data.short_voice || data.long_voice);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto scrollbar-thin">
        <DialogHeader>
          <div className="flex items-center gap-3.5">
            <span
              aria-hidden
              className="relative grid h-12 w-12 shrink-0 place-items-center overflow-hidden rounded-xl"
              style={{
                background:
                  "linear-gradient(135deg, color-mix(in oklch, hsl(var(--primary)) 34%, hsl(var(--background))), hsl(var(--background)))",
                border: "1px solid hsl(var(--primary) / .30)",
              }}
            >
              {initial ? (
                <span className="font-display text-[22px] font-bold leading-none text-primary">
                  {initial}
                </span>
              ) : (
                <Youtube className="h-5 w-5 text-primary" strokeWidth={1.8} />
              )}
              <span
                aria-hidden
                className="absolute inset-0 opacity-10 text-primary"
                style={{
                  backgroundImage:
                    "repeating-linear-gradient(45deg, currentColor 0, currentColor 1px, transparent 0, transparent 6px)",
                }}
              />
            </span>
            <div className="min-w-0">
              <DialogTitle className="text-[17px] leading-tight">
                {editing ? "Editar canal" : "Nuevo canal de YouTube"}
              </DialogTitle>
              <DialogDescription className="mt-0.5">
                Se guarda en{" "}
                <code className="rounded bg-muted px-1 py-px font-mono text-[11px]">
                  .mp/youtube.json
                </code>{" "}
                y se usa en cada generación.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 py-1">
          {/* ── Identidad ──────────────────────────────────────────── */}
          <FormSection
            icon={IdCard}
            accent="var(--primary)"
            title="Identidad del canal"
            hint="Cómo se llama y de qué trata. Define el tono de cada guion."
          >
            <Field className="sm:col-span-2" label="Nickname" htmlFor="nickname" required>
              <Input
                id="nickname"
                value={data.nickname}
                onChange={(e) => update("nickname", e.target.value)}
                placeholder="Ej: André Crónicas"
              />
            </Field>

            <Field
              className="sm:col-span-2"
              label="Niche / temática"
              htmlFor="niche"
              hint="La IA lo usa para elegir temas y enfocar el contenido."
            >
              <Textarea
                id="niche"
                rows={2}
                value={data.niche}
                onChange={(e) => update("niche", e.target.value)}
                placeholder="Curiosidades de la historia, civilizaciones antiguas..."
              />
            </Field>

            <Field label="Idioma" htmlFor="language" icon={Globe}>
              <Input
                id="language"
                value={data.language}
                onChange={(e) => update("language", e.target.value)}
                placeholder="español"
              />
            </Field>

            <Field label="Hook profile" htmlFor="hook_profile" icon={Sparkles}>
              <Select
                value={data.hook_profile || "__default__"}
                onValueChange={(v) =>
                  update("hook_profile", v === "__default__" ? "" : v)
                }
              >
                <SelectTrigger id="hook_profile">
                  <SelectValue placeholder="(default)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__default__">(default)</SelectItem>
                  {HOOK_PROFILES.filter(Boolean).map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          </FormSection>

          {/* ── Conexión con YouTube ───────────────────────────────── */}
          <FormSection
            icon={Link2}
            accent="var(--accent)"
            title="Conexión con YouTube"
            hint="Datos técnicos para sincronizar y subir. Solo se tocan una vez."
          >
            <Field
              className="sm:col-span-2"
              label="Handle de YouTube"
              htmlFor="youtube_handle"
              icon={AtSign}
              hint="Identificador público. La sincronización descarga el listado de videos publicados."
            >
              <Input
                id="youtube_handle"
                value={data.youtube_handle || ""}
                onChange={(e) => update("youtube_handle", e.target.value)}
                placeholder="@TuCanal o https://www.youtube.com/@TuCanal"
                className="font-mono text-xs"
              />
            </Field>

            <Field
              className="sm:col-span-2"
              label="Perfil de Firefox"
              htmlFor="firefox_profile"
              icon={FolderOpen}
              hint="Debe estar pre-loggeado en YouTube Studio para que la subida funcione."
            >
              <Input
                id="firefox_profile"
                value={data.firefox_profile}
                onChange={(e) => update("firefox_profile", e.target.value)}
                placeholder="C:\\Users\\you\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\xxxx"
                className="font-mono text-xs"
              />
            </Field>
          </FormSection>

          {/* ── Voz y estilo ───────────────────────────────────────── */}
          <FormSection
            icon={AudioLines}
            accent="var(--gold)"
            title="Voz y estilo visual"
            hint="Define cómo suena la narración y el look de las imágenes generadas."
          >
            <Field label="Voz para Shorts" htmlFor="short_voice">
              <VoiceSelect
                id="short_voice"
                value={data.short_voice || ""}
                voices={voices}
                onChange={(v) => update("short_voice", v)}
              />
            </Field>

            <Field label="Voz para Long Videos" htmlFor="long_voice">
              <VoiceSelect
                id="long_voice"
                value={data.long_voice || ""}
                voices={voices}
                onChange={(v) => update("long_voice", v)}
              />
            </Field>

            <div
              className="sm:col-span-2 flex items-center justify-between gap-4 rounded-lg px-3 py-2.5"
              style={{
                border: "1px solid hsl(var(--border) / .10)",
                background: hasVoice ? "hsl(var(--gold) / .05)" : "transparent",
              }}
            >
              <div className="min-w-0 space-y-0.5">
                <Label className="text-[13px]">Voice drama</Label>
                <p className="text-[11.5px] leading-snug text-muted-foreground">
                  Activa modulación más expresiva y emocional en el TTS.
                </p>
              </div>
              <Switch
                checked={!!data.voice_drama}
                onCheckedChange={(v) => update("voice_drama", v)}
              />
            </div>

            <Field
              className="sm:col-span-2"
              label="Estilo de imagen"
              htmlFor="image_style"
              icon={Palette}
              hint="Se añade como sufijo a cada prompt de imagen. Vacío = el modelo decide."
            >
              <Textarea
                id="image_style"
                rows={3}
                value={data.image_style}
                onChange={(e) => update("image_style", e.target.value)}
                placeholder="cinematic photorealistic, dramatic lighting, classical aesthetic"
              />
            </Field>
          </FormSection>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancelar
          </Button>
          <Button variant="brand" onClick={submit} disabled={saving} className="gap-2">
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            {editing ? "Guardar cambios" : "Crear canal"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Layout helpers — grouped sections with a coloured icon header, and a labeled
// field wrapper so every input reads consistently.
// ─────────────────────────────────────────────────────────────────────────────
interface FormSectionProps {
  icon: typeof Youtube;
  title: string;
  hint?: string;
  accent: string;
  children: React.ReactNode;
}

function FormSection({ icon: Icon, title, hint, accent, children }: FormSectionProps) {
  return (
    <section className="soft-panel p-4">
      <div className="flex items-start gap-3">
        <span
          className="grid h-9 w-9 shrink-0 place-items-center rounded-lg"
          style={{
            background: `hsl(${accent} / .12)`,
            border: `1px solid hsl(${accent} / .25)`,
            color: `hsl(${accent})`,
          }}
        >
          <Icon className="h-4 w-4" strokeWidth={1.9} />
        </span>
        <div className="min-w-0">
          <h3 className="font-display text-[14px] font-semibold leading-tight text-foreground">
            {title}
          </h3>
          {hint && (
            <p className="mt-0.5 text-[11.5px] leading-snug text-muted-foreground">
              {hint}
            </p>
          )}
        </div>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">{children}</div>
    </section>
  );
}

interface FieldProps {
  label: string;
  htmlFor?: string;
  hint?: string;
  required?: boolean;
  icon?: typeof Youtube;
  className?: string;
  children: React.ReactNode;
}

function Field({ label, htmlFor, hint, required, icon: Icon, className, children }: FieldProps) {
  return (
    <div className={"space-y-1.5 " + (className ?? "")}>
      <Label htmlFor={htmlFor} className="flex items-center gap-1.5 text-[12.5px]">
        {Icon && <Icon className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.8} />}
        {label}
        {required && <span className="text-accent">*</span>}
      </Label>
      {children}
      {hint && (
        <p className="text-[11px] leading-snug text-muted-foreground">{hint}</p>
      )}
    </div>
  );
}

interface VoiceSelectProps {
  id: string;
  value: string;
  voices: Voice[];
  onChange: (v: string) => void;
}

function VoiceSelect({ id, value, voices, onChange }: VoiceSelectProps) {
  // If the saved value isn't in the curated list, surface it as an "orphan"
  // option so the user can still see what's saved (and pick a new one
  // without silently losing the previous value).
  const knownIds = new Set(voices.map((v) => v.voice_id));
  const knownAliases = new Set(voices.map((v) => v.alias));
  const isOrphan = !!value && !knownIds.has(value) && !knownAliases.has(value);

  // Group voices by language tag for readability.
  const grouped = voices.reduce<Record<string, Voice[]>>((acc, v) => {
    (acc[v.language] ||= []).push(v);
    return acc;
  }, {});
  const languages = Object.keys(grouped).sort();

  // The preview endpoint expects a real Edge-TTS voice id. The select stores
  // voice_id directly, but legacy/orphan values may be an alias. Resolve those
  // back to a voice_id so the play button still works.
  const aliasToId = new Map(voices.map((v) => [v.alias, v.voice_id]));
  const previewId = knownIds.has(value) ? value : aliasToId.get(value) ?? "";

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "playing">("idle");

  const stop = () => {
    audioRef.current?.pause();
    audioRef.current = null;
    setState("idle");
  };

  const preview = () => {
    if (state !== "idle") {
      stop();
      return;
    }
    if (!previewId) {
      toast.error("Selecciona una voz válida para escucharla.");
      return;
    }
    setState("loading");
    const audio = new Audio(api.voicePreviewUrl(previewId));
    audioRef.current = audio;
    audio.onplaying = () => setState("playing");
    audio.onended = stop;
    audio.onerror = () => {
      toast.error("No se pudo generar el preview de esta voz.");
      stop();
    };
    audio.play().catch(() => {
      toast.error("No se pudo reproducir el audio.");
      stop();
    });
  };

  // Stop any playback when the component unmounts (dialog closed).
  useEffect(() => () => stop(), []);

  return (
    <div className="flex items-center gap-2">
      <Select
        value={value || "__none__"}
        onValueChange={(v) => {
          stop();
          onChange(v === "__none__" ? "" : v);
        }}
      >
        <SelectTrigger id={id} className="flex-1">
          <SelectValue placeholder="(seleccionar voz)" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__none__">(sin voz — usa el default del sistema)</SelectItem>
          {isOrphan && (
            <SelectItem value={value}>
              {value} <span className="text-xs text-muted-foreground">(personalizada)</span>
            </SelectItem>
          )}
          {languages.map((lang) => (
            <div key={lang}>
              <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-muted-foreground">
                {lang}
              </div>
              {grouped[lang].map((v) => (
                <SelectItem key={v.voice_id} value={v.voice_id}>
                  {v.alias}{" "}
                  <span className="text-xs text-muted-foreground">— {v.voice_id}</span>
                </SelectItem>
              ))}
            </div>
          ))}
        </SelectContent>
      </Select>
      <Button
        type="button"
        variant="outline"
        size="icon"
        onClick={preview}
        disabled={!previewId && state === "idle"}
        title={state === "idle" ? "Escuchar voz" : "Detener"}
        className="shrink-0"
      >
        {state === "loading" ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : state === "playing" ? (
          <Square className="h-4 w-4" />
        ) : (
          <Play className="h-4 w-4" />
        )}
      </Button>
    </div>
  );
}
