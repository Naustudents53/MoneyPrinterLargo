"use client";

import { useEffect, useState } from "react";
import { Layers, Plus, ChevronLeft } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { Chip } from "@/components/ui/chip";

interface SeriesItem {
  id: string;
  name: string;
  title_template?: string;
  thumbnail_overlay?: string;
  thumbnail_font?: string;
  script_brief?: string;
  section_count?: number;
}

const SERIES_THEMES = [
  { bg: "hsl(20,40%,8%)",  accent: "#E8A24F" },
  { bg: "hsl(210,40%,8%)", accent: "#60A5FA" },
  { bg: "hsl(270,30%,8%)", accent: "#C084FC" },
  { bg: "hsl(150,30%,8%)", accent: "#4ADE80" },
];

export function SeriesFrame() {
  const [items, setItems] = useState<SeriesItem[]>([]);
  const [openIdx, setOpenIdx] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<{ series: SeriesItem[] }>("/api/config/series")
      .then((d) => {
        if (!cancelled) setItems(d.series || []);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  if (openIdx !== null && items[openIdx]) {
    const s = items[openIdx];
    const theme = SERIES_THEMES[openIdx % SERIES_THEMES.length];
    return (
      <div className="flex flex-col h-full overflow-hidden">
        <div className="flex-1 overflow-auto p-8">
          <button
            type="button"
            onClick={() => setOpenIdx(null)}
            className="flex items-center gap-1 text-[12px] text-[var(--color-text-tertiary)] mb-6 hover:text-[var(--color-text-primary)]"
          >
            <ChevronLeft size={14} />
            All series
          </button>

          <div className="flex gap-6 mb-8 items-start">
            <div
              className="w-[120px] h-[120px] rounded-[12px] flex items-center justify-center shrink-0"
              style={{
                background: `linear-gradient(135deg, ${theme.bg}, var(--color-surf-1))`,
                border: `1px solid ${theme.accent}22`,
              }}
            >
              <Layers size={40} style={{ color: theme.accent, opacity: 0.6 }} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[28px] font-bold tracking-[-0.03em] text-[var(--color-text-primary)] mb-1">
                {s.name}
              </div>
              <div className="flex gap-2 flex-wrap mb-3">
                <Chip color={theme.accent}>{s.section_count ?? 0} sections</Chip>
                {s.thumbnail_font && <Chip>{s.thumbnail_font}</Chip>}
                {s.title_template && (
                  <Chip>{s.title_template.slice(0, 28)}{s.title_template.length > 28 ? "…" : ""}</Chip>
                )}
              </div>
              <div className="mt-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--color-text-tertiary)] mb-2">
                  Script Brief
                </div>
                <div
                  className="rounded-md p-3 font-mono text-[11px] leading-[1.6] text-[var(--color-text-secondary)]"
                  style={{
                    background: "var(--color-surf-2)",
                    border: "1px solid var(--color-hairline)",
                  }}
                >
                  {s.script_brief || "—"}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto p-8">
      {items.length === 0 ? (
        <div className="rounded-[12px] border border-dashed border-[var(--color-hairline)] py-16 text-center text-[13px] text-[var(--color-text-tertiary)]">
          No series configured. Add them to <span className="font-mono">config.json</span> under <span className="font-mono">series</span>.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
          {items.map((s, i) => {
            const theme = SERIES_THEMES[i % SERIES_THEMES.length];
            return (
              <button
                key={s.id || s.name}
                type="button"
                onClick={() => setOpenIdx(i)}
                className="rounded-[12px] p-5 text-left transition-all duration-150 flex flex-col gap-[14px] cursor-pointer"
                style={{
                  background: "var(--color-surf-2)",
                  border: "1px solid var(--color-hairline)",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = `${theme.accent}44`;
                  e.currentTarget.style.background = theme.bg;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "var(--color-hairline)";
                  e.currentTarget.style.background = "var(--color-surf-2)";
                }}
              >
                <div
                  className="h-[100px] rounded-md relative flex items-center justify-center overflow-hidden"
                  style={{
                    background: `linear-gradient(135deg, ${theme.bg}, var(--color-surf-1))`,
                    border: `1px solid ${theme.accent}22`,
                  }}
                >
                  <div
                    className="absolute inset-0 stripes-soft"
                    style={{ opacity: 0.07 }}
                    aria-hidden
                  />
                  <Layers size={28} style={{ color: theme.accent, opacity: 0.55 }} />
                </div>
                <div>
                  <div className="text-[15px] font-semibold text-[var(--color-text-primary)] tracking-[-0.02em] mb-1 truncate">
                    {s.name}
                  </div>
                  <div className="flex gap-2 flex-wrap">
                    <Chip color={theme.accent}>{s.section_count ?? 0} sections</Chip>
                    {s.thumbnail_font && <Chip>{s.thumbnail_font}</Chip>}
                  </div>
                </div>
                {s.script_brief && (
                  <div className="font-mono text-[10px] text-[var(--color-text-tertiary)] truncate">
                    {s.script_brief}
                  </div>
                )}
              </button>
            );
          })}

          <div
            className="rounded-[12px] py-5 px-5 cursor-pointer flex flex-col items-center justify-center gap-2 transition-all duration-150 min-h-[200px]"
            style={{
              background: "transparent",
              border: "2px dashed var(--color-hairline)",
              color: "var(--color-text-tertiary)",
            }}
          >
            <Plus size={22} />
            <span className="text-[12px]">New Series</span>
            <span className="text-[10px] text-center max-w-[160px]">
              Add a series block to <span className="font-mono">config.json</span>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
