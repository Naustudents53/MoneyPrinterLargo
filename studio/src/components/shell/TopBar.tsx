"use client";

import { useEffect, useState } from "react";
import { ChevronDown, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiFetch, listJobs } from "@/lib/api";

interface ConfigSummary {
  llm_provider: string;
  ollama_model: string;
  gemini_models: string[];
  ollama_base_url: string;
}

const PROVIDER_LABELS: Record<string, string> = {
  ollama: "Ollama",
  gemini: "Gemini",
  pollinations: "Pollinations",
};

export function TopBar({
  title,
  showNew = true,
  newHref = "/shorts",
}: {
  title?: string;
  showNew?: boolean;
  newHref?: string;
}) {
  const router = useRouter();
  const [llmOpen, setLlmOpen] = useState(false);
  const [config, setConfig] = useState<ConfigSummary | null>(null);
  const [renderQueue, setRenderQueue] = useState(0);

  useEffect(() => {
    let cancelled = false;
    apiFetch<ConfigSummary>("/api/config")
      .then((cfg) => {
        if (!cancelled) setConfig(cfg);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      try {
        const data = await listJobs();
        if (cancelled) return;
        const count = data.jobs.filter(
          (j) => j.status === "running" || j.status === "uploading",
        ).length;
        setRenderQueue(count);
      } catch {
        /* ignore */
      } finally {
        if (!cancelled) timer = setTimeout(tick, 4000);
      }
    };
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  const providerLabel = config ? PROVIDER_LABELS[config.llm_provider] || config.llm_provider : "—";
  const providerModel =
    config?.llm_provider === "ollama"
      ? config?.ollama_model || "default"
      : (config?.gemini_models?.[0] ?? "default");

  return (
    <header
      className="flex items-center h-14 px-6 gap-3 shrink-0 relative z-20"
      style={{
        background: "var(--color-surf-1)",
        borderBottom: "1px solid var(--color-hairline)",
      }}
    >
      <span className="text-[14px] font-medium text-[var(--color-text-primary)] tracking-[-0.01em] flex-1 truncate">
        {title ?? "Studio"}
      </span>

      {/* LLM provider chip */}
      <div className="relative">
        <button
          type="button"
          onClick={() => setLlmOpen((s) => !s)}
          className="flex items-center gap-[6px] rounded-md px-[10px] py-[5px] text-[12px] transition-colors duration-150"
          style={{
            background: "var(--color-surf-2)",
            border: "1px solid var(--color-hairline)",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--color-amber-ring)")}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--color-hairline)")}
        >
          <span
            className="block w-[6px] h-[6px] rounded-full"
            style={{ background: config ? "var(--color-success)" : "var(--color-text-tertiary)" }}
          />
          <span className="font-mono text-[var(--color-text-secondary)]">{providerLabel}</span>
          <span className="text-[var(--color-text-tertiary)]">·</span>
          <span className="font-mono text-[var(--color-text-primary)] truncate max-w-[160px]">
            {providerModel}
          </span>
          <ChevronDown size={12} className="text-[var(--color-text-tertiary)]" />
        </button>
        {llmOpen && (
          <div
            className="absolute top-[calc(100%+6px)] right-0 w-[240px] rounded-[10px] p-2 z-50 shadow-[0_16px_40px_rgba(0,0,0,0.5)]"
            style={{
              background: "var(--color-surf-2)",
              border: "1px solid var(--color-hairline)",
            }}
          >
            {(["ollama", "gemini", "pollinations"] as const).map((id) => {
              const active = config?.llm_provider === id;
              const subtitle =
                id === "ollama"
                  ? config?.ollama_model || "deepseek"
                  : id === "gemini"
                  ? config?.gemini_models?.[0] ?? "gemini-2.5-flash"
                  : "openai";
              return (
                <Link
                  key={id}
                  href="/settings"
                  onClick={() => setLlmOpen(false)}
                  className="flex items-center gap-[6px] px-[10px] py-[6px] rounded-md text-[12px] font-mono cursor-pointer"
                  style={{
                    background: active ? "var(--color-amber-dim)" : "transparent",
                    color: active ? "var(--color-amber)" : "var(--color-text-secondary)",
                  }}
                >
                  {active && (
                    <span
                      className="block w-[5px] h-[5px] rounded-full"
                      style={{ background: "var(--color-success)" }}
                    />
                  )}
                  {PROVIDER_LABELS[id]} · {subtitle}
                </Link>
              );
            })}
          </div>
        )}
      </div>

      {/* Render queue */}
      {renderQueue > 0 && (
        <Link
          href="/tasks"
          className="flex items-center gap-[6px] rounded-md px-[10px] py-[5px] text-[12px]"
          style={{
            background: "var(--color-warning-bg)",
            border: "1px solid rgba(245,158,11,0.30)",
            color: "var(--color-warning)",
          }}
        >
          <span
            className="block w-[6px] h-[6px] rounded-full animate-pulse-slow"
            style={{ background: "var(--color-warning)" }}
          />
          {renderQueue} rendering
        </Link>
      )}

      {/* New */}
      {showNew && (
        <button
          type="button"
          onClick={() => router.push(newHref)}
          className="flex items-center gap-[6px] rounded-md px-[14px] py-[7px] text-[13px] font-semibold tracking-[-0.01em] transition-opacity duration-150"
          style={{
            background: "var(--color-amber)",
            color: "#0B0B0D",
            border: "none",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.opacity = "0.88")}
          onMouseLeave={(e) => (e.currentTarget.style.opacity = "1")}
        >
          <Plus size={14} strokeWidth={2.5} />
          New
        </button>
      )}
    </header>
  );
}
