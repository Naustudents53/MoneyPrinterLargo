"use client";

import { useEffect, useState } from "react";
import { Check, AlertCircle, Edit, Plus } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { Chip } from "@/components/ui/chip";
import { PlatformGlyph } from "@/components/ui/platform-glyph";

interface AccountFull {
  id: string;
  nickname: string;
  niche: string;
  language: string;
  image_style: string;
  short_voice: string;
  long_voice: string;
  profile_ready: boolean;
  firefox_profile: string;
  hook_profile?: string;
  voice_drama?: boolean;
  platform?: string;
}

const PLATFORM_BORDER: Record<string, string> = {
  youtube: "#FF4444",
  twitter: "#A8A29E",
};

export function AccountsFrame() {
  const [accounts, setAccounts] = useState<AccountFull[]>([]);
  const [editId, setEditId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<{ accounts: AccountFull[] }>("/api/accounts")
      .then((d) => {
        if (cancelled) return;
        setAccounts(
          (d.accounts || []).map((a) => ({
            ...a,
            platform: a.platform || "youtube",
          })),
        );
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex-1 overflow-auto p-8">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-4">
        {accounts.map((acc) => {
          const platform = acc.platform || "youtube";
          const borderColor = PLATFORM_BORDER[platform] || "#A8A29E";
          const editing = acc.id === editId;
          return (
            <div
              key={acc.id}
              className="rounded-[12px] p-5 flex flex-col gap-[14px] transition-colors duration-150"
              style={{
                background: "var(--color-surf-2)",
                border: "1px solid var(--color-hairline)",
              }}
              onMouseEnter={(e) =>
                (e.currentTarget.style.borderColor = "var(--color-border-default)")
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.borderColor = "var(--color-hairline)")
              }
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-10 h-10 rounded-full flex items-center justify-center text-[14px] font-bold text-[var(--color-text-primary)] shrink-0"
                  style={{
                    background: "linear-gradient(135deg, var(--color-surf-3), var(--color-base))",
                    border: `2px solid ${borderColor}33`,
                  }}
                >
                  {acc.nickname.slice(0, 2).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-[6px]">
                    <span className="text-[14px] font-semibold text-[var(--color-text-primary)] tracking-[-0.01em] truncate">
                      {acc.nickname}
                    </span>
                    <PlatformGlyph platform={platform} size={16} />
                  </div>
                  <div className="text-[11px] text-[var(--color-text-tertiary)] truncate">
                    {acc.niche || "—"}
                  </div>
                </div>
                <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">
                  {acc.language || "—"}
                </span>
              </div>

              <div className="flex gap-2 flex-wrap">
                {acc.short_voice && (
                  <div className="flex flex-col gap-[3px]">
                    <span className="text-[9px] uppercase tracking-[0.06em] text-[var(--color-text-tertiary)]">
                      Short voice
                    </span>
                    <Chip color="#E8A24F">{acc.short_voice}</Chip>
                  </div>
                )}
                {acc.long_voice && acc.long_voice !== "—" && (
                  <div className="flex flex-col gap-[3px]">
                    <span className="text-[9px] uppercase tracking-[0.06em] text-[var(--color-text-tertiary)]">
                      Long voice
                    </span>
                    <Chip color="#60A5FA">{acc.long_voice}</Chip>
                  </div>
                )}
              </div>

              {acc.image_style && (
                <div>
                  <div className="text-[9px] uppercase tracking-[0.06em] text-[var(--color-text-tertiary)] mb-1">
                    Image style
                  </div>
                  <div
                    className="font-mono text-[10px] text-[var(--color-text-secondary)] leading-[1.5] line-clamp-2 px-2 py-[5px] rounded-md"
                    style={{
                      background: "var(--color-surf-3)",
                      border: "1px solid var(--color-hairline)",
                    }}
                  >
                    {acc.image_style}
                  </div>
                </div>
              )}

              <div className="flex items-center gap-2">
                <div
                  className="flex items-center gap-[5px] flex-1 px-2 py-[5px] rounded-md"
                  style={{
                    background: acc.profile_ready
                      ? "var(--color-success-bg)"
                      : "var(--color-error-bg)",
                    border: `1px solid ${
                      acc.profile_ready ? "rgba(74,222,128,0.27)" : "rgba(248,113,113,0.27)"
                    }`,
                  }}
                >
                  {acc.profile_ready ? (
                    <Check size={11} className="text-[var(--color-success)]" />
                  ) : (
                    <AlertCircle size={11} className="text-[var(--color-error)]" />
                  )}
                  <span
                    className="text-[10px]"
                    style={{
                      color: acc.profile_ready
                        ? "var(--color-success)"
                        : "var(--color-error)",
                    }}
                  >
                    {acc.profile_ready ? "Firefox profile linked" : "Profile not linked"}
                  </span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setEditId(editing ? null : acc.id)}
                className="w-full px-2 py-[7px] rounded-md text-[12px] flex items-center justify-center gap-[6px] transition-all duration-150"
                style={{
                  background: editing ? "var(--color-amber-dim)" : "transparent",
                  color: editing ? "var(--color-amber)" : "var(--color-text-secondary)",
                  border: `1px solid ${
                    editing ? "var(--color-amber-ring)" : "var(--color-hairline)"
                  }`,
                }}
              >
                <Edit size={12} />
                {editing ? "Editing…" : "Edit"}
              </button>
            </div>
          );
        })}

        <div
          className="rounded-[12px] p-5 cursor-pointer flex flex-col items-center justify-center gap-2 transition-all duration-150 min-h-[260px]"
          style={{
            background: "transparent",
            border: "2px dashed var(--color-hairline)",
            color: "var(--color-text-tertiary)",
          }}
        >
          <Plus size={22} />
          <span className="text-[12px]">Add Account</span>
          <span className="text-[10px] text-center max-w-[160px]">
            YouTube, Twitter, or Affiliate
          </span>
        </div>
      </div>
    </div>
  );
}
