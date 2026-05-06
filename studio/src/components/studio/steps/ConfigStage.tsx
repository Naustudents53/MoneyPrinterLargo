"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { Loader2, Sparkles, Rocket, ChevronDown, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { getSeries, getAccounts, getVoices, getPresets, createPreset, createJob } from "@/lib/api";
import { useProductionStore } from "@/stores/production";

interface ConfigStageProps {
  onComplete?: () => void;
}

interface SeriesItem {
  id: string;
  name: string;
}

interface AccountItem {
  id: string;
  nickname: string;
}

interface VoiceItem {
  id: string;
  alias: string;
}

interface PresetItem {
  id: string;
  name: string;
}

export function ConfigStage({ onComplete }: ConfigStageProps) {
  const [topic, setTopic] = useState("");
  const [seriesList, setSeriesList] = useState<SeriesItem[]>([]);
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [voices, setVoices] = useState<VoiceItem[]>([]);
  const [presets, setPresets] = useState<PresetItem[]>([]);
  const [selectedSeries, setSelectedSeries] = useState("");
  const [selectedAccount, setSelectedAccount] = useState("");
  const [selectedVoice, setSelectedVoice] = useState("");
  const [imageStyle, setImageStyle] = useState("");
  const [imageMode, setImageMode] = useState<"AI" | "Real photos">("AI");
  const [selectedPreset, setSelectedPreset] = useState("");

  const production = useProductionStore((s) =>
    s.productions.find((p) => p.id === s.currentProductionId)
  );
  const prodType = production?.config.type || "short";

  const [targetDuration, setTargetDuration] = useState<60 | 120 | 180>(
    production?.config.targetDuration ?? 60
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingPreset, setSavingPreset] = useState(false);

  useEffect(() => {
    let mounted = true;
    Promise.all([
      getSeries().catch(() => [] as SeriesItem[]),
      getAccounts().catch(() => [] as AccountItem[]),
      getVoices().catch(() => ({ voices: [] as VoiceItem[], default: "" })),
      getPresets().catch(() => [] as PresetItem[]),
    ]).then(([series, accountsData, voicesData, presets]) => {
      if (!mounted) return;
      if (Array.isArray(series)) setSeriesList(series as SeriesItem[]);
      if (Array.isArray(accountsData)) setAccounts(accountsData as AccountItem[]);
      if (voicesData && Array.isArray(voicesData.voices)) {
        setVoices(voicesData.voices as VoiceItem[]);
        if (voicesData.default) setSelectedVoice(voicesData.default);
      }
      if (Array.isArray(presets)) setPresets(presets as PresetItem[]);
    }).catch(() => {
      if (mounted) setError("Some configuration data failed to load.");
    }).finally(() => {
      if (mounted) setLoading(false);
    });
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    useProductionStore.getState().updateConfig({ targetDuration });
  }, [targetDuration]);

  const handleSavePreset = useCallback(async () => {
    try {
      setSavingPreset(true);
      await createPreset({
        name: `Preset ${presets.length + 1}`,
        config: {
          type: prodType,
          voice_id: selectedVoice,
          image_style: imageStyle,
          image_mode: imageMode === "AI" ? "ai" : "photos",
        },
      });
    } catch {
      // silent fail for now
    } finally {
      setSavingPreset(false);
    }
  }, [presets.length, selectedVoice, imageStyle, imageMode, prodType]);

  if (loading) {
    return (
      <div className="flex flex-col gap-4 p-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <motion.div
            key={i}
            className="h-12 rounded-xl bg-surface-overlay animate-pulse"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0.4, 0.8, 0.4] }}
            transition={{ duration: 1.5, repeat: Infinity, delay: i * 0.1 }}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      {error && (
        <div className="rounded-lg border border-error/20 bg-error/10 px-4 py-3 text-sm text-error">
          {error}
        </div>
      )}

      {/* Topic */}
      <div className="flex flex-col gap-2">
        <label className="text-sm text-text-secondary">Topic</label>
        <input
          className="rounded-xl border border-border-subtle bg-surface-raised px-4 py-3 text-sm text-text-primary outline-none transition-colors focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30"
          placeholder="Enter video topic..."
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        />
      </div>

      {/* Series */}
      <div className="flex flex-col gap-2">
        <label className="text-sm text-text-secondary">Series</label>
        <div className="relative">
          <select
            className="w-full appearance-none rounded-xl border border-border-subtle bg-surface-raised px-4 py-3 pr-10 text-sm text-text-primary outline-none transition-colors focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30"
            value={selectedSeries}
            onChange={(e) => setSelectedSeries(e.target.value)}
          >
            <option value="">Select series</option>
            {seriesList.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
        </div>
      </div>

      {/* Account */}
      <div className="flex flex-col gap-2">
        <label className="text-sm text-text-secondary">Account</label>
        <div className="relative">
          <select
            className="w-full appearance-none rounded-xl border border-border-subtle bg-surface-raised px-4 py-3 pr-10 text-sm text-text-primary outline-none transition-colors focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30"
            value={selectedAccount}
            onChange={(e) => setSelectedAccount(e.target.value)}
          >
            <option value="">Select account</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>{a.nickname}</option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
        </div>
      </div>

      {/* Voice */}
      <div className="flex flex-col gap-2">
        <label className="text-sm text-text-secondary">Voice</label>
        <div className="relative">
          <select
            className="w-full appearance-none rounded-xl border border-border-subtle bg-surface-raised px-4 py-3 pr-10 text-sm text-text-primary outline-none transition-colors focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30"
            value={selectedVoice}
            onChange={(e) => setSelectedVoice(e.target.value)}
          >
            <option value="">Select voice</option>
            {voices.map((v) => (
              <option key={v.id} value={v.id}>{v.alias}</option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
        </div>
      </div>

      {/* Image Style */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <label className="text-sm text-text-secondary">Image Style</label>
          <div className="group relative">
            <Info size={14} className="text-text-tertiary" />
            <div className="pointer-events-none absolute left-1/2 top-full z-20 mt-1 w-56 -translate-x-1/2 rounded-lg border border-border-subtle bg-surface-overlay p-2 text-xs text-text-tertiary opacity-0 shadow-float transition-opacity group-hover:opacity-100">
              Examples: cinematic, neon cyberpunk, retro VHS, minimalist 3D
            </div>
          </div>
        </div>
        <input
          className="rounded-xl border border-border-subtle bg-surface-raised px-4 py-3 text-sm text-text-primary outline-none transition-colors focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30"
          placeholder="e.g. cinematic neon cyberpunk"
          value={imageStyle}
          onChange={(e) => setImageStyle(e.target.value)}
        />
      </div>

      {/* Image Mode */}
      <div className="flex flex-col gap-2">
        <label className="text-sm text-text-secondary">Image Mode</label>
        <div className="relative">
          <select
            className="w-full appearance-none rounded-xl border border-border-subtle bg-surface-raised px-4 py-3 pr-10 text-sm text-text-primary outline-none transition-colors focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30"
            value={imageMode}
            onChange={(e) => setImageMode(e.target.value as "AI" | "Real photos")}
          >
            <option value="AI">AI Generated</option>
            <option value="Real photos">Real Photos</option>
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
        </div>
      </div>

      {/* Duration selector (short only) */}
      {prodType === "short" && (
        <div className="flex flex-col gap-2">
          <label className="text-sm text-text-secondary">Duration</label>
          <div className="flex gap-2">
            {([60, 120, 180] as const).map((sec) => (
              <button
                key={sec}
                type="button"
                onClick={() => {
                  setTargetDuration(sec);
                  useProductionStore.getState().updateConfig({ targetDuration: sec });
                }}
                className={cn(
                  "flex-1 rounded-xl border px-3 py-2 text-sm font-medium transition-colors",
                  targetDuration === sec
                    ? "border-accent-purple bg-accent-purple/20 text-accent-purple"
                    : "border-border-subtle bg-surface-raised text-text-secondary hover:bg-surface-overlay hover:text-text-primary"
                )}
              >
                {sec === 60 ? "1 min" : sec === 120 ? "2 min" : "3 min"}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Preset */}
      <div className="flex flex-col gap-2">
        <label className="text-sm text-text-secondary">Preset</label>
        <div className="relative">
          <select
            className="w-full appearance-none rounded-xl border border-border-subtle bg-surface-raised px-4 py-3 pr-10 text-sm text-text-primary outline-none transition-colors focus:border-accent-purple focus:ring-1 focus:ring-accent-purple/30"
            value={selectedPreset}
            onChange={(e) => setSelectedPreset(e.target.value)}
          >
            <option value="">Select preset</option>
            {presets.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2">
        <motion.button
          className={cn(
            "flex items-center gap-2 rounded-xl border border-border-subtle px-4 py-2.5 text-sm text-text-secondary transition-colors",
            "hover:bg-surface-overlay hover:text-text-primary"
          )}
          onClick={handleSavePreset}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.97 }}
          disabled={savingPreset}
        >
          {savingPreset ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          Save as Preset
        </motion.button>

        <motion.button
          className={cn(
            "flex items-center gap-2 rounded-xl bg-accent-purple px-5 py-2.5 text-sm font-medium text-white shadow-glow-purple transition-colors",
            "hover:bg-accent-purple-deep"
          )}
          onClick={async () => {
            useProductionStore.getState().updateConfig({
              topic,
              seriesId: selectedSeries,
              accountId: selectedAccount,
              voiceId: selectedVoice,
              imageStyle,
              imageMode: imageMode === "AI" ? "ai" : "photos",
              presetId: selectedPreset,
              targetDuration: prodType === "short" ? targetDuration : undefined,
            });
            useProductionStore.getState().clearArtifacts();
            const { job_id } = await createJob({
              type: prodType,
              topic,
              series_id: selectedSeries,
              account_id: selectedAccount,
              voice_id: selectedVoice,
              image_mode: imageMode === "AI" ? "ai" : "photos",
              image_style: imageStyle,
              preset_id: selectedPreset,
              target_duration: prodType === "short" ? targetDuration : undefined,
            });
            useProductionStore.getState().setJobId(job_id);
            onComplete?.();
          }}
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
        >
          <Rocket size={16} />
          Start Generation
        </motion.button>
      </div>
    </div>
  );
}
