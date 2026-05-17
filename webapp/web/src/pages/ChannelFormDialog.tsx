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
import { Loader2, Play, Square } from "lucide-react";
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto scrollbar-thin">
        <DialogHeader>
          <DialogTitle>
            {editing ? "Editar canal" : "Nuevo canal de YouTube"}
          </DialogTitle>
          <DialogDescription>
            Estos datos se guardan en <code className="text-xs">.mp/youtube.json</code> y se
            usan en cada generación.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2 space-y-2">
            <Label htmlFor="nickname">Nickname *</Label>
            <Input
              id="nickname"
              value={data.nickname}
              onChange={(e) => update("nickname", e.target.value)}
              placeholder="Ej: André Crónicas"
            />
          </div>

          <div className="sm:col-span-2 space-y-2">
            <Label htmlFor="niche">Niche / temática</Label>
            <Textarea
              id="niche"
              rows={2}
              value={data.niche}
              onChange={(e) => update("niche", e.target.value)}
              placeholder="Curiosidades de la historia, civilizaciones antiguas..."
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="language">Idioma</Label>
            <Input
              id="language"
              value={data.language}
              onChange={(e) => update("language", e.target.value)}
              placeholder="español"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="hook_profile">Hook profile</Label>
            <Select
              value={data.hook_profile || "__default__"}
              onValueChange={(v) => update("hook_profile", v === "__default__" ? "" : v)}
            >
              <SelectTrigger>
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
          </div>

          <div className="sm:col-span-2 space-y-2">
            <Label htmlFor="youtube_handle">Handle de YouTube</Label>
            <Input
              id="youtube_handle"
              value={data.youtube_handle || ""}
              onChange={(e) => update("youtube_handle", e.target.value)}
              placeholder="@TuCanal o https://www.youtube.com/@TuCanal"
              className="font-mono text-xs"
            />
            <p className="text-xs text-muted-foreground">
              Identificador público del canal. Lo usa la sincronización con
              YouTube para descargar el listado de videos publicados.
            </p>
          </div>

          <div className="sm:col-span-2 space-y-2">
            <Label htmlFor="firefox_profile">Path al perfil de Firefox</Label>
            <Input
              id="firefox_profile"
              value={data.firefox_profile}
              onChange={(e) => update("firefox_profile", e.target.value)}
              placeholder="C:\\Users\\you\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\xxxx"
              className="font-mono text-xs"
            />
            <p className="text-xs text-muted-foreground">
              Debe estar pre-loggeado en YouTube Studio para que la subida funcione.
            </p>
          </div>

          <div className="sm:col-span-2 space-y-2">
            <Label htmlFor="image_style">Estilo de imagen (sufijo libre)</Label>
            <Textarea
              id="image_style"
              rows={3}
              value={data.image_style}
              onChange={(e) => update("image_style", e.target.value)}
              placeholder="cinematic photorealistic, dramatic lighting, classical aesthetic"
            />
            <p className="text-xs text-muted-foreground">
              Se añade como sufijo a cada prompt de imagen. Vacío = el modelo decide el estilo.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="short_voice">Voz para Shorts</Label>
            <VoiceSelect
              id="short_voice"
              value={data.short_voice || ""}
              voices={voices}
              onChange={(v) => update("short_voice", v)}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="long_voice">Voz para Long Videos</Label>
            <VoiceSelect
              id="long_voice"
              value={data.long_voice || ""}
              voices={voices}
              onChange={(v) => update("long_voice", v)}
            />
          </div>

          <div className="sm:col-span-2 flex items-center justify-between rounded-lg border border-border p-3">
            <div className="space-y-0.5">
              <Label>Voice drama (énfasis emocional)</Label>
              <p className="text-xs text-muted-foreground">
                Activa modulación más expresiva en el TTS.
              </p>
            </div>
            <Switch
              checked={!!data.voice_drama}
              onCheckedChange={(v) => update("voice_drama", v)}
            />
          </div>
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
