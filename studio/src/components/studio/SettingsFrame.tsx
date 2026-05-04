"use client";

import { useEffect, useState } from "react";
import { Cpu, Zap, Globe, Check, Settings as SettingsIcon } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface ConfigFull {
  llm_provider: string;
  ollama_base_url: string;
  ollama_model: string;
  gemini_models: string[];
  nanobanana2_model: string;
  nanobanana2_aspect_ratio: string;
  tts_voice: string;
  tts_provider: string;
  stt_provider: string;
  whisper_model: string;
  font: string;
  imagemagick_path: string;
  threads: number;
  movie_max_duration_seconds: number;
  movie_chunk_minutes: number;
}

const TABS = [
  { id: "general",   label: "General" },
  { id: "llm",       label: "LLM Providers" },
  { id: "image",     label: "Image Gen" },
  { id: "voices",    label: "Voices" },
  { id: "subtitles", label: "Subtitles" },
  { id: "music",     label: "Music" },
  { id: "storage",   label: "Storage" },
  { id: "advanced",  label: "Advanced" },
];

interface ProviderDef {
  id: "ollama" | "gemini" | "pollinations";
  name: string;
  desc: string;
  Icon: React.ElementType;
  fields: { key: string; label: string; placeholder: string; mono?: boolean; secret?: boolean }[];
}

const PROVIDERS: ProviderDef[] = [
  {
    id: "ollama",
    name: "Ollama",
    desc: "Local inference — no API key required",
    Icon: Cpu,
    fields: [{ key: "ollama_base_url", label: "Base URL", placeholder: "http://127.0.0.1:11434", mono: true }],
  },
  {
    id: "gemini",
    name: "Gemini",
    desc: "Google cloud cascade — fast and accurate",
    Icon: Zap,
    fields: [{ key: "gemini_api_key", label: "API Key", placeholder: "AIzaSy...", mono: true, secret: true }],
  },
  {
    id: "pollinations",
    name: "Pollinations",
    desc: "Free tier — no API key needed",
    Icon: Globe,
    fields: [],
  },
];

export function SettingsFrame() {
  const [activeTab, setActiveTab] = useState("llm");
  const [config, setConfig] = useState<ConfigFull | null>(null);
  const [activeProvider, setActiveProvider] = useState<ProviderDef["id"]>("ollama");
  const [testState, setTestState] = useState<Record<string, "idle" | "loading" | "done" | "error">>({});
  const [testOutput, setTestOutput] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;
    apiFetch<ConfigFull>("/api/config")
      .then((c) => {
        if (cancelled) return;
        setConfig(c);
        setActiveProvider((c.llm_provider as ProviderDef["id"]) || "ollama");
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const runTest = (provId: ProviderDef["id"]) => {
    setTestState((s) => ({ ...s, [provId]: "loading" }));
    setTestOutput((o) => ({ ...o, [provId]: "" }));
    // Simulate streaming. Replace with a real /api/llm/test endpoint when added.
    const words = ["Hola!", " El", " universo", " tiene", " ~13.8", " mil", " millones", " de", " años."];
    let i = 0;
    const interval = setInterval(() => {
      if (i >= words.length) {
        clearInterval(interval);
        setTestState((s) => ({ ...s, [provId]: "done" }));
        return;
      }
      setTestOutput((o) => ({ ...o, [provId]: (o[provId] || "") + words[i] }));
      i++;
    }, 180);
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Tabs */}
      <div
        className="flex gap-0 px-6 border-b shrink-0 overflow-x-auto"
        style={{ borderColor: "var(--color-hairline)" }}
      >
        {TABS.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className="px-4 py-[10px] bg-transparent border-0 cursor-pointer text-[13px] whitespace-nowrap transition-colors duration-150"
              style={{
                color: active ? "var(--color-text-primary)" : "var(--color-text-tertiary)",
                fontWeight: active ? 600 : 400,
                borderBottom: `2px solid ${active ? "var(--color-amber)" : "transparent"}`,
                marginBottom: -1,
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-auto p-8">
        {activeTab === "llm" && (
          <div className="max-w-[780px]">
            <div className="mb-7">
              <div className="text-[18px] font-bold tracking-[-0.02em] text-[var(--color-text-primary)] mb-1">
                LLM Providers
              </div>
              <div className="text-[13px] text-[var(--color-text-secondary)]">
                Active provider runs script generation, metadata, and tweet copy. Edit{" "}
                <span className="font-mono text-[12px]">config.json</span> to persist changes.
              </div>
            </div>

            <div className="flex flex-col gap-4">
              {PROVIDERS.map((prov) => {
                const isActive = activeProvider === prov.id;
                const ts = testState[prov.id] || "idle";
                const Icon = prov.Icon;
                return (
                  <div
                    key={prov.id}
                    className="rounded-[12px] overflow-hidden transition-all duration-150"
                    style={{
                      border: `1px solid ${
                        isActive ? "rgba(232,162,79,0.27)" : "var(--color-hairline)"
                      }`,
                      background: isActive ? "var(--color-amber-dim)" : "var(--color-surf-2)",
                    }}
                  >
                    <div className="px-5 py-4 flex items-center gap-[14px]">
                      <div
                        className="w-9 h-9 rounded-md flex items-center justify-center shrink-0"
                        style={{
                          background: isActive
                            ? "rgba(232,162,79,0.13)"
                            : "var(--color-surf-3)",
                          border: `1px solid ${
                            isActive ? "rgba(232,162,79,0.27)" : "var(--color-hairline)"
                          }`,
                        }}
                      >
                        <Icon
                          size={16}
                          style={{
                            color: isActive ? "var(--color-amber)" : "var(--color-text-secondary)",
                          }}
                        />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-[14px] font-semibold text-[var(--color-text-primary)]">
                            {prov.name}
                          </span>
                          {isActive && (
                            <span
                              className="text-[10px] font-semibold px-[7px] py-[2px] rounded text-[var(--color-amber)] tracking-[0.04em]"
                              style={{
                                background: "rgba(232,162,79,0.13)",
                                border: "1px solid rgba(232,162,79,0.27)",
                              }}
                            >
                              ACTIVE
                            </span>
                          )}
                        </div>
                        <div className="text-[12px] text-[var(--color-text-tertiary)]">
                          {prov.desc}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => setActiveProvider(prov.id)}
                        className="px-[14px] py-[6px] rounded-md text-[12px] cursor-pointer transition-all duration-150"
                        style={{
                          border: `1px solid ${isActive ? "var(--color-amber)" : "var(--color-hairline)"}`,
                          background: isActive ? "var(--color-amber)" : "transparent",
                          color: isActive ? "#0B0B0D" : "var(--color-text-secondary)",
                          fontWeight: isActive ? 600 : 400,
                        }}
                      >
                        {isActive ? "Active" : "Set active"}
                      </button>
                    </div>

                    <div
                      className="px-5 pb-5 flex flex-col gap-3"
                      style={{ borderTop: "1px solid var(--color-hairline)", paddingTop: 16 }}
                    >
                      {/* Model */}
                      <div>
                        <label className="block text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--color-text-tertiary)] mb-[6px]">
                          Model
                        </label>
                        <select
                          defaultValue={
                            prov.id === "ollama"
                              ? config?.ollama_model
                              : prov.id === "gemini"
                              ? config?.gemini_models?.[0]
                              : "openai"
                          }
                          className="rounded-md px-3 py-[7px] text-[12px] outline-none cursor-pointer w-[300px] font-mono"
                          style={{
                            background: "var(--color-surf-3)",
                            border: "1px solid var(--color-hairline)",
                            color: "var(--color-text-primary)",
                          }}
                        >
                          {prov.id === "ollama" && config?.ollama_model && (
                            <option value={config.ollama_model}>{config.ollama_model}</option>
                          )}
                          {prov.id === "gemini" &&
                            (config?.gemini_models || []).map((m) => (
                              <option key={m} value={m}>
                                {m}
                              </option>
                            ))}
                          {prov.id === "pollinations" && (
                            <>
                              <option value="openai">openai</option>
                              <option value="mistral">mistral</option>
                              <option value="llama">llama</option>
                            </>
                          )}
                        </select>
                      </div>

                      {/* Fields */}
                      {prov.fields.map((field) => (
                        <div key={field.key}>
                          <label className="block text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--color-text-tertiary)] mb-[6px]">
                            {field.label}
                          </label>
                          <input
                            type={field.secret ? "password" : "text"}
                            placeholder={field.placeholder}
                            defaultValue={
                              field.key === "ollama_base_url"
                                ? config?.ollama_base_url || ""
                                : ""
                            }
                            className="rounded-md px-3 py-[7px] text-[12px] outline-none w-[320px]"
                            style={{
                              background: "var(--color-surf-3)",
                              border: "1px solid var(--color-hairline)",
                              color: "var(--color-text-primary)",
                              fontFamily: field.mono ? "var(--font-mono)" : "inherit",
                            }}
                          />
                        </div>
                      ))}

                      {/* Test connection */}
                      <div>
                        <div className="flex items-center gap-[10px]">
                          <button
                            type="button"
                            onClick={() => runTest(prov.id)}
                            disabled={ts === "loading"}
                            className="px-[14px] py-[6px] rounded-md text-[12px] flex items-center gap-[6px] transition-all duration-150"
                            style={{
                              cursor: ts === "loading" ? "wait" : "pointer",
                              background: "var(--color-surf-3)",
                              color: "var(--color-text-secondary)",
                              border: "1px solid var(--color-hairline)",
                            }}
                          >
                            {ts === "loading" ? (
                              <>
                                <span
                                  className="block w-[10px] h-[10px] rounded-full animate-spin"
                                  style={{
                                    border: "2px solid var(--color-text-tertiary)",
                                    borderTopColor: "var(--color-amber)",
                                  }}
                                />
                                Testing…
                              </>
                            ) : ts === "done" ? (
                              <>
                                <Check size={12} className="text-[var(--color-success)]" />
                                Test again
                              </>
                            ) : (
                              <>
                                <Zap size={12} />
                                Test connection
                              </>
                            )}
                          </button>
                          {ts === "done" && (
                            <span className="text-[11px] text-[var(--color-success)] flex items-center gap-1">
                              <Check size={11} /> Connected
                            </span>
                          )}
                        </div>
                        {testOutput[prov.id] && (
                          <div
                            className="mt-2 px-3 py-2 rounded-md font-mono text-[11px] leading-[1.7] text-[var(--color-text-secondary)]"
                            style={{
                              background: "var(--color-surf-3)",
                              border: "1px solid var(--color-hairline)",
                            }}
                          >
                            {testOutput[prov.id]}
                            {ts === "loading" && <span className="animate-blink-cursor">▌</span>}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {activeTab === "general" && config && (
          <div className="max-w-[780px] flex flex-col gap-4">
            <KeyValueRow label="LLM provider" value={config.llm_provider} />
            <KeyValueRow label="TTS provider" value={config.tts_provider} />
            <KeyValueRow label="TTS voice" value={config.tts_voice} />
            <KeyValueRow label="STT provider" value={config.stt_provider} />
            <KeyValueRow label="Whisper model" value={config.whisper_model} />
            <KeyValueRow label="Image gen" value={config.nanobanana2_model || "nanobanana2"} />
            <KeyValueRow label="Aspect ratio" value={config.nanobanana2_aspect_ratio} />
            <KeyValueRow label="Threads" value={String(config.threads)} />
            <KeyValueRow label="ImageMagick" value={config.imagemagick_path || "—"} mono />
            <KeyValueRow
              label="Movie max duration"
              value={`${config.movie_max_duration_seconds}s`}
            />
            <KeyValueRow label="Movie chunk minutes" value={`${config.movie_chunk_minutes} min`} />
          </div>
        )}

        {activeTab !== "llm" && activeTab !== "general" && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-[var(--color-text-tertiary)]">
            <SettingsIcon size={32} className="opacity-40" />
            <span className="text-[13px]">
              {TABS.find((t) => t.id === activeTab)?.label} settings
            </span>
            <span className="text-[11px]">
              Edit <span className="font-mono">config.json</span> to change these for now.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function KeyValueRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div
      className="flex items-center justify-between px-4 py-3 rounded-md"
      style={{
        background: "var(--color-surf-2)",
        border: "1px solid var(--color-hairline)",
      }}
    >
      <span className="text-[12px] font-medium uppercase tracking-[0.05em] text-[var(--color-text-tertiary)]">
        {label}
      </span>
      <span
        className="text-[12px] text-[var(--color-text-primary)]"
        style={{ fontFamily: mono ? "var(--font-mono)" : undefined }}
      >
        {value}
      </span>
    </div>
  );
}
