/**
 * API client for the MoneyPrinter Largo backend.
 *
 * Vite dev server proxies /api → http://127.0.0.1:8000 (see vite.config.ts).
 * In production builds, set VITE_API_BASE if the backend lives elsewhere.
 */

const BASE = (import.meta.env.VITE_API_BASE as string) || "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // ignore
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

// ---------- Types ----------

// Allowed short-video duration presets, mirroring SHORT_DURATION_PRESETS in
// src/classes/duration_presets.py. Keep these in sync if the backend list
// changes — the API rejects anything else with HTTP 400.
export const SHORT_DURATION_OPTIONS = [60, 120, 180] as const;
export type ShortDurationSeconds = (typeof SHORT_DURATION_OPTIONS)[number];

// Mirror of HOOK_PROFILES keys in src/classes/YouTube.py. Keep these in sync —
// the backend rejects anything else with HTTP 400.
export const HOOK_PROFILE_OPTIONS = ["educational", "storytelling"] as const;
export type HookProfile = (typeof HOOK_PROFILE_OPTIONS)[number];
export const SHORT_RENDER_PROFILE_OPTIONS = ["quality", "fast", "turbo"] as const;
export type ShortRenderProfile = (typeof SHORT_RENDER_PROFILE_OPTIONS)[number];
export const RETENTION_MODE_OPTIONS = ["standard", "maxima_retencion"] as const;
export type RetentionMode = (typeof RETENTION_MODE_OPTIONS)[number];
export const UPLOAD_PLATFORM_OPTIONS = ["youtube", "tiktok", "facebook"] as const;
export type UploadPlatform = (typeof UPLOAD_PLATFORM_OPTIONS)[number];

export interface PlatformUploadState {
  status: "pending" | "uploaded" | "failed" | string;
  url?: string | null;
  updated_at?: string | null;
  error?: string;
}

export interface Channel {
  id: string;
  nickname: string;
  firefox_profile: string;
  niche: string;
  language: string;
  image_style: string;
  short_voice: string;
  long_voice: string;
  hook_profile: string;
  voice_drama: boolean;
  youtube_handle: string;
  videos_count: number;
  // Populated by scripts/sync_youtube_cache.py. `null` means the channel has
  // never been synced — render as "—" so it doesn't look like a real "0 subs".
  subscriber_count: number | null;
  stats_synced_at: string;
}

export interface ChannelInput {
  nickname: string;
  firefox_profile?: string;
  niche?: string;
  language?: string;
  image_style?: string;
  short_voice?: string;
  long_voice?: string;
  hook_profile?: string;
  voice_drama?: boolean;
  youtube_handle?: string;
}

export interface ChannelVideo {
  index: number;
  title: string;
  description: string;
  subject: string;
  url: string;
  date: string;
  is_short: boolean;
  // Engagement counters from `scripts/sync_youtube_cache.py --refresh-meta`.
  // -1 means "no data" (yt-dlp couldn't read it / RYD didn't have the video).
  view_count?: number;
  like_count?: number;
  comment_count?: number;
  dislike_count?: number;
  stats_synced_at?: string;
  platform_uploads?: Partial<Record<UploadPlatform, PlatformUploadState>>;
}

export interface RetentionLabVideo {
  title: string;
  subject: string;
  url: string;
  date: string;
  views: number | null;
  likes: number | null;
  comments: number | null;
  stats_synced_at: string;
  performance: "winner" | "weak" | "normal" | "unknown";
}

export interface RetentionLabTerm {
  term: string;
  count: number;
  avg_views: number;
  latest_views: number | null;
  winner_count: number;
  weak_count: number;
  examples: string[];
  reason?: string;
}

export interface RetentionLabChannel {
  channel_id: string;
  channel_nickname: string;
  niche: string;
  language: string;
  stats: {
    videos: number;
    shorts: number;
    known_views: number;
    unknown_views: number;
    winners: number;
    weak: number;
    avg_views: number;
    median_views: number;
  };
  winners: RetentionLabVideo[];
  weak_videos: RetentionLabVideo[];
  burned_topics: RetentionLabTerm[];
  winning_terms: RetentionLabTerm[];
  recommendations: string[];
}

export interface RetentionLabResponse {
  generated_at: string;
  aggregate: {
    channels: number;
    shorts: number;
    known_views: number;
    unknown_views: number;
    winners: number;
    weak: number;
  };
  channels: RetentionLabChannel[];
}

export interface TwitterAccount {
  id: string;
  nickname: string;
  firefox_profile: string;
  topic: string;
  posts_count: number;
}

export interface TwitterPost {
  index: number;
  content: string;
  date: string;
}

export interface SystemStats {
  channels_count: number;
  twitter_accounts_count: number;
  products_count: number;
  total_videos: number;
  total_posts: number;
  mp4_count: number;
  mp4_bytes: number;
  mp4_mb: number;
  recent_videos: {
    channel_id: string;
    channel_nickname: string;
    title: string;
    url: string;
    date: string;
  }[];
}

export interface SystemInfo {
  root_dir: string;
  mp_dir_exists: boolean;
  config_exists: boolean;
  llm_provider: string;
  tts_voice: string;
  image_aspect_ratio: string;
  short_render_profile?: ShortRenderProfile;
  stt_provider: string;
  headless: boolean;
  version: string;
  ts: string;
}

export interface ConfigField {
  key: string;
  label: string;
  type: "bool" | "int" | "str" | "secret";
  group: string;
}

export interface ConfigResponse {
  raw: Record<string, unknown>;
  fields: ConfigField[];
}

export interface SeriesEntry {
  id: string;
  name: string;
  title_template?: string;
  thumbnail_overlay?: string;
  script_brief?: string;
  section_themes?: string[];
}

export interface Mp4FileEntry {
  name: string;
  size_mb: number;
  mtime: string;
  /** True when the matching <name>.manifest.json has uploaded:true. */
  uploaded?: boolean;
  uploaded_url?: string | null;
  subject?: string | null;
  platform_uploads?: Partial<Record<UploadPlatform, PlatformUploadState>>;
  social_summary?: {
    quality_gate?: {
      status?: string;
      score?: number;
      width?: number;
      height?: number;
      duration_seconds?: number;
      checks?: { name: string; status: string; message: string }[];
    };
    safe_zone?: { status?: string };
    trend_terms?: string[];
    caption_scores?: Partial<Record<UploadPlatform, number>>;
  };
  retention_summary?: {
    version?: number;
    generated_at?: string;
    status?: string;
    score?: number;
    hook?: string;
    hook_score?: number;
    intro_status?: string;
    loop_status?: string;
    hot_words?: string[];
    micro_hooks_count?: number;
    visual_status?: string;
    analytics?: {
      winning_terms?: string[];
      burned_terms?: string[];
    };
  };
}

export interface ThumbnailEntry {
  name: string;
  size_kb: number;
  mtime: string;
}

export interface JobSummary {
  id: string;
  title: string;
  status: "running" | "done" | "error";
  started_at: string;
  finished_at: string | null;
  elapsed: number;
  rc: number | null;
  last_line: string;
  log_lines: number;
  // Set by the backend only for YouTube generation jobs so the reattach UI
  // can offer "Subir a YouTube" against the original channel. Null on jobs
  // where the action wouldn't make sense (upload-last itself, sync, tweet).
  channel_id: string | null;
  kind: "short" | "long" | null;
}

export interface Voice {
  alias: string;
  voice_id: string;
  language: string;
}

export interface LLMModel {
  id: string;
  label: string;
  provider: "gemini" | "ollama" | "openai" | "claude" | "pollinations";
  description: string;
}

export interface LLMModelList {
  models: LLMModel[];
  default: string;
  active_provider: string;
}

export type OpenAIReasoningEffort = "low" | "medium" | "high" | "xhigh";
export type ClaudeReasoningEffort = "low" | "medium" | "high" | "xhigh" | "max";
export type LLMReasoningEffort = OpenAIReasoningEffort | ClaudeReasoningEffort;
export type LLMRunMode = "standard" | "fast";
export type LLMProvider = "ollama" | "gemini" | "openai" | "claude" | "pollinations";
export type ImageProvider = "auto" | "leonardo" | "openai" | "gemini";

export interface HookStyle {
  id: string;       // "<profile>::<name>" — round-trips via MP_HOOK_STYLE_OVERRIDE
  profile: string;  // "educational" | "storytelling" | ...
  name: string;     // "You-are-there immersion"
  example: string;  // short snippet (truncated server-side)
}

export interface BatchJobItem {
  channel_id: string;
  kind: "short" | "long";
  custom_topic?: string;
  image_mode?: "ai" | "photos";
  image_provider?: ImageProvider | "";
  auto_upload?: boolean;
  series_id?: string;
  llm_provider?: LLMProvider | "";
  llm_reasoning_effort?: LLMReasoningEffort | "";
  llm_mode?: LLMRunMode | "";
  model?: string;
  sentence_length?: number;
  hook_style?: string;
  render_profile?: ShortRenderProfile;
  retention_mode?: RetentionMode;
}

export interface BatchJobResult {
  channel_id: string;
  channel_nickname?: string;
  kind?: string;
  job_id?: string;
  ok: boolean;
  error?: string;
}

export interface PreviewScript {
  id: string;
  subject: string;
  script: string;
}

export interface PhotoUploadResponse {
  id: string;
  count: number;
  files: string[];
}

export interface PhotoPromptOption {
  id: string;
  label: string;
  description: string;
}

export interface PhotoPromptOptions {
  styles: PhotoPromptOption[];
  aspect_ratios: PhotoPromptOption[];
}

export interface PhotoPromptRequest {
  channel_id?: string;
  topic?: string;
  count?: number;
  style?: string;
  aspect_ratio?: string;
  language?: string;
  llm_provider?: LLMProvider | "";
  llm_model?: string;
  retention_mode?: RetentionMode;
}

export interface PhotoPromptResponse {
  topic: string;
  generated_topic: boolean;
  style: string;
  aspect_ratio: string;
  count: number;
  text: string;
  filename: string;
  channel_id: string;
  channel_nickname: string;
  script: string;
  prompts: string[];
}

// Auto-sync scheduler ------------------------------------------------------

export type AutoSyncTier = "light" | "recent" | "full";

export interface AutoSyncConfig {
  enabled: boolean;
  light_enabled: boolean;
  light_interval_minutes: number;
  recent_enabled: boolean;
  recent_interval_minutes: number;
  recent_video_count: number;
  full_enabled: boolean;
  full_interval_minutes: number;
}

export interface AutoSyncTierState {
  last_run_at?: string;
  last_run_started_at?: string;
  next_run_at?: string;
  last_status?: "ok" | "error" | "running" | "disabled";
  last_message?: string;
  consecutive_failures?: number;
}

export interface AutoSyncStatus {
  running: boolean;
  config: AutoSyncConfig;
  tiers: Partial<Record<AutoSyncTier, AutoSyncTierState>>;
  logs: Partial<Record<AutoSyncTier, string[]>>;
}

// ---------- Endpoints ----------

export const api = {
  // System
  systemInfo: () => request<SystemInfo>("/api/system/info"),
  systemStats: () => request<SystemStats>("/api/system/stats"),

  // Channels
  listChannels: () => request<Channel[]>("/api/channels"),
  getChannel: (id: string) => request<Channel>(`/api/channels/${id}`),
  createChannel: (data: ChannelInput) =>
    request<Channel>("/api/channels", { method: "POST", body: JSON.stringify(data) }),
  updateChannel: (id: string, data: ChannelInput) =>
    request<Channel>(`/api/channels/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteChannel: (id: string) =>
    request<{ ok: boolean }>(`/api/channels/${id}`, { method: "DELETE" }),

  // Videos
  listVideos: (id: string) => request<ChannelVideo[]>(`/api/channels/${id}/videos`),
  deleteVideo: (id: string, params: { url?: string; date?: string }) => {
    const qs = new URLSearchParams();
    if (params.url) qs.set("url", params.url);
    if (params.date) qs.set("date", params.date);
    return request<{ ok: boolean }>(
      `/api/channels/${id}/videos?${qs.toString()}`,
      { method: "DELETE" }
    );
  },
  clearVideos: (id: string) =>
    request<{ ok: boolean }>(`/api/channels/${id}/videos/clear`, { method: "POST" }),
  editVideo: (
    id: string,
    payload: {
      url: string;
      date: string;
      title?: string;
      subject?: string;
      description?: string;
      is_short?: boolean;
    }
  ) =>
    request<{ ok: boolean; video: ChannelVideo }>(`/api/channels/${id}/videos`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  markAllVideosKind: (id: string, kind: "short" | "long") =>
    request<{ ok: boolean; updated: number }>(
      `/api/channels/${id}/videos/mark-all?kind=${kind}`,
      { method: "POST" }
    ),
  retentionLab: (channelId?: string) => {
    const qs = new URLSearchParams();
    if (channelId) qs.set("channel_id", channelId);
    const query = qs.toString();
    return request<RetentionLabResponse>(`/api/retention-lab${query ? "?" + query : ""}`);
  },

  // Twitter
  listTwitterAccounts: () => request<TwitterAccount[]>("/api/twitter/accounts"),
  createTwitterAccount: (data: { nickname: string; firefox_profile?: string; topic?: string }) =>
    request<TwitterAccount>("/api/twitter/accounts", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateTwitterAccount: (id: string, data: { nickname: string; firefox_profile?: string; topic?: string }) =>
    request<TwitterAccount>(`/api/twitter/accounts/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteTwitterAccount: (id: string) =>
    request<{ ok: boolean }>(`/api/twitter/accounts/${id}`, { method: "DELETE" }),
  listTwitterPosts: (id: string) => request<TwitterPost[]>(`/api/twitter/accounts/${id}/posts`),

  // Series
  listSeries: () => request<SeriesEntry[]>("/api/series"),

  // Voices (curated Edge-TTS list — used by ChannelFormDialog selects)
  listVoices: () => request<{ voices: Voice[] }>("/api/voices"),
  voicePreviewUrl: (voiceId: string) =>
    `${BASE}/api/voices/preview?voice_id=${encodeURIComponent(voiceId)}`,

  // LLM models (used by Generate page selector)
  listLLMModels: () => request<LLMModelList>("/api/llm/models"),

  // Photo prompt generator
  photoPromptOptions: () => request<PhotoPromptOptions>("/api/photo-prompts/options"),
  generatePhotoPrompts: (data: PhotoPromptRequest) =>
    request<PhotoPromptResponse>("/api/photo-prompts/generate", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Hook styles (used by Generate page hook selector)
  listHookStyles: () => request<{ styles: HookStyle[] }>("/api/llm/hook-styles"),

  // Topic suggestions — returns N ideas tailored to the channel's niche.
  suggestTopics: (channelId: string, params: {
    n?: number;
    model?: string;
    llm_provider?: LLMProvider | "";
    llm_reasoning_effort?: LLMReasoningEffort | "";
    llm_mode?: LLMRunMode | "";
  } = {}) => {
    const qs = new URLSearchParams();
    if (params.n) qs.set("n", String(params.n));
    if (params.model) qs.set("model", params.model);
    if (params.llm_provider) qs.set("llm_provider", params.llm_provider);
    if (params.llm_reasoning_effort) qs.set("llm_reasoning_effort", params.llm_reasoning_effort);
    if (params.llm_mode) qs.set("llm_mode", params.llm_mode);
    return request<{ topics: string[] }>(
      `/api/channels/${channelId}/suggest-topics?${qs.toString()}`,
    );
  },

  // Preview-script artifacts (used by "Vista previa" flow)
  readPreview: (id: string) => request<PreviewScript>(`/api/preview/${id}`),
  savePreview: (id: string, data: { subject: string; script: string }) =>
    request<{ ok: boolean }>(`/api/preview/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  scriptVoicePreviewUrl: (id: string, params: {
    channel_id: string;
    kind?: "short" | "long";
    retention_mode?: RetentionMode;
  }) => {
    const qs = new URLSearchParams();
    qs.set("channel_id", params.channel_id);
    if (params.kind) qs.set("kind", params.kind);
    if (params.retention_mode && params.retention_mode !== "standard") {
      qs.set("retention_mode", params.retention_mode);
    }
    return `${BASE}/api/preview/${id}/voice?${qs.toString()}`;
  },

  uploadPhotos: async (files: File[]) => {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    const res = await fetch(`${BASE}/api/photo-video/uploads`, {
      method: "POST",
      body,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const json = await res.json();
        detail = json.detail || JSON.stringify(json);
      } catch {
        // ignore
      }
      throw new Error(`${res.status}: ${detail}`);
    }
    return res.json() as Promise<PhotoUploadResponse>;
  },

  // Batch generation (spawns N parallel jobs)
  generateBatch: (jobs: BatchJobItem[]) =>
    request<{ jobs: BatchJobResult[]; spawned: number }>("/api/generate-batch", {
      method: "POST",
      body: JSON.stringify({ jobs }),
    }),

  // Auto-sync scheduler
  getAutoSyncStatus: () => request<AutoSyncStatus>("/api/auto-sync/status"),
  triggerAutoSync: (tier: AutoSyncTier) =>
    request<{ ok: boolean; tier: string }>(`/api/auto-sync/run/${tier}`, {
      method: "POST",
    }),
  updateAutoSyncConfig: (patch: Partial<AutoSyncConfig>) =>
    request<{ ok: boolean; auto_sync: AutoSyncConfig }>("/api/auto-sync/config", {
      method: "PUT",
      body: JSON.stringify(patch),
    }),

  // Config
  getConfig: () => request<ConfigResponse>("/api/config"),
  updateConfig: (data: Record<string, unknown>) =>
    request<{ ok: boolean; raw: Record<string, unknown> }>("/api/config", {
      method: "PUT",
      body: JSON.stringify({ data }),
    }),

  // Storage
  listMp4: () => request<Mp4FileEntry[]>("/api/storage/mp4"),
  deleteMp4: (name: string) =>
    request<{ ok: boolean }>(`/api/storage/mp4/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),
  clearMp4: () =>
    request<{ ok: boolean; deleted: number }>("/api/storage/mp4/clear", { method: "POST" }),
  markMp4Uploaded: (name: string) =>
    request<{ ok: boolean; uploaded_url: string | null }>(
      `/api/storage/mp4/${encodeURIComponent(name)}/mark-uploaded`,
      { method: "POST" },
    ),

  // Deprecated — kept as a thin adapter so legacy callers still compile.
  // New code should use `listLLMModels()` and group by `provider` directly.
  listLlmModels: async () => {
    const data = await request<LLMModelList>("/api/llm/models");
    const buckets: { ollama: string[]; gemini: string[]; openai: string[]; claude: string[]; pollinations: string[] } = {
      ollama: [],
      gemini: [],
      openai: [],
      claude: [],
      pollinations: [],
    };
    for (const m of data.models || []) {
      if (m.provider in buckets) buckets[m.provider].push(m.id);
    }
    return { ...buckets, errors: {} as Record<string, string> };
  },

  // SSE URLs (used by EventSource directly)
  generateUrl(id: string, params: {
    kind: "short" | "long";
    custom_topic?: string;
    image_mode?: "ai" | "photos";
    image_provider?: ImageProvider | "";
    auto_upload?: boolean;
    upload_platforms?: UploadPlatform[];
    series_id?: string;
    duration_seconds?: ShortDurationSeconds;
    render_profile?: ShortRenderProfile;
    llm_provider?: LLMProvider | "";
    llm_model?: string;
    llm_reasoning_effort?: LLMReasoningEffort | "";
    llm_mode?: LLMRunMode | "";
    hook_profile?: HookProfile | "";
    model?: string;
    sentence_length?: number;
    hook_style?: string;
    script_file?: string;
    photo_upload_id?: string;
    retention_mode?: RetentionMode;
  }): string {
    const qs = new URLSearchParams();
    qs.set("kind", params.kind);
    if (params.custom_topic) qs.set("custom_topic", params.custom_topic);
    if (params.image_mode) qs.set("image_mode", params.image_mode);
    if (params.image_provider) qs.set("image_provider", params.image_provider);
    if (params.auto_upload) qs.set("auto_upload", "true");
    if (params.upload_platforms?.length) {
      qs.set("upload_platforms", params.upload_platforms.join(","));
    }
    if (params.series_id) qs.set("series_id", params.series_id);
    if (params.kind === "short" && params.duration_seconds) {
      qs.set("duration_seconds", String(params.duration_seconds));
    }
    if (params.kind === "short" && params.render_profile) {
      qs.set("render_profile", params.render_profile);
    }
    if (params.llm_provider) qs.set("llm_provider", params.llm_provider);
    if (params.llm_model) qs.set("llm_model", params.llm_model);
    if (params.llm_reasoning_effort) qs.set("llm_reasoning_effort", params.llm_reasoning_effort);
    if (params.llm_mode) qs.set("llm_mode", params.llm_mode);
    if (params.hook_profile) qs.set("hook_profile", params.hook_profile);
    if (params.model) qs.set("model", params.model);
    if (params.sentence_length && params.sentence_length > 0) {
      qs.set("sentence_length", String(params.sentence_length));
    }
    if (params.hook_style) qs.set("hook_style", params.hook_style);
    if (params.script_file) qs.set("script_file", params.script_file);
    if (params.photo_upload_id) qs.set("photo_upload_id", params.photo_upload_id);
    if (params.kind === "short" && params.retention_mode && params.retention_mode !== "standard") {
      qs.set("retention_mode", params.retention_mode);
    }
    return `${BASE}/api/channels/${id}/generate?${qs.toString()}`;
  },
  previewScriptUrl(id: string, params: {
    custom_topic?: string;
    model?: string;
    llm_provider?: LLMProvider | "";
    llm_reasoning_effort?: LLMReasoningEffort | "";
    llm_mode?: LLMRunMode | "";
    sentence_length?: number;
    duration_seconds?: ShortDurationSeconds;
    hook_style?: string;
    retention_mode?: RetentionMode;
  } = {}): string {
    const qs = new URLSearchParams();
    qs.set("kind", "short");
    if (params.custom_topic) qs.set("custom_topic", params.custom_topic);
    if (params.model) qs.set("model", params.model);
    if (params.llm_provider) qs.set("llm_provider", params.llm_provider);
    if (params.llm_reasoning_effort) qs.set("llm_reasoning_effort", params.llm_reasoning_effort);
    if (params.llm_mode) qs.set("llm_mode", params.llm_mode);
    if (params.sentence_length && params.sentence_length > 0) {
      qs.set("sentence_length", String(params.sentence_length));
    }
    if (params.duration_seconds) qs.set("duration_seconds", String(params.duration_seconds));
    if (params.hook_style) qs.set("hook_style", params.hook_style);
    if (params.retention_mode && params.retention_mode !== "standard") {
      qs.set("retention_mode", params.retention_mode);
    }
    return `${BASE}/api/channels/${id}/preview-script?${qs.toString()}`;
  },
  uploadLastUrl: (
    id: string,
    kind: "short" | "long" = "short",
    uploadPlatforms: UploadPlatform[] = ["youtube"],
  ) => {
    const qs = new URLSearchParams();
    qs.set("kind", kind);
    if (uploadPlatforms.length) qs.set("upload_platforms", uploadPlatforms.join(","));
    return `${BASE}/api/channels/${id}/upload-last?${qs.toString()}`;
  },
  syncYouTubeUrl: (params: {
    channel_id?: string;
    prune?: boolean;
    add_missing?: boolean;
    refresh_meta?: boolean;
  } = {}) => {
    const qs = new URLSearchParams();
    if (params.channel_id) qs.set("channel_id", params.channel_id);
    qs.set("prune", String(params.prune ?? true));
    qs.set("add_missing", String(params.add_missing ?? true));
    qs.set("refresh_meta", String(params.refresh_meta ?? true));
    return `${BASE}/api/youtube/sync?${qs.toString()}`;
  },
  postTweetUrl: (id: string) => `${BASE}/api/twitter/accounts/${id}/post`,

  // Job control / monitoring
  stopJob: (jobId: string) =>
    request<{ ok: boolean }>(`/api/jobs/${jobId}/stop`, { method: "POST" }),
  listJobs: (includeFinished = false) =>
    request<JobSummary[]>(`/api/jobs?include_finished=${includeFinished}`),
  getJob: (id: string) => request<JobSummary>(`/api/jobs/${id}`),
  jobStreamUrl: (id: string) => `${BASE}/api/jobs/${id}/stream`,

  // Raw video stream (for <video> player)
  mp4RawUrl: (name: string) => `${BASE}/api/storage/mp4/${encodeURIComponent(name)}/raw`,

  // Thumbnails
  listThumbnails: () => request<ThumbnailEntry[]>("/api/thumbnails"),
  deleteThumbnail: (name: string) =>
    request<{ ok: boolean }>(`/api/thumbnails/${encodeURIComponent(name)}`, { method: "DELETE" }),
  clearThumbnails: () =>
    request<{ ok: boolean; deleted: number }>("/api/thumbnails/clear", { method: "POST" }),
  thumbnailRawUrl: (name: string) => `${BASE}/api/thumbnails/${encodeURIComponent(name)}/raw`,
  thumbnailGenerateUrl: (params: { topic: string; text: string; visual?: string }) => {
    const qs = new URLSearchParams();
    qs.set("topic", params.topic);
    qs.set("text", params.text);
    if (params.visual) qs.set("visual", params.visual);
    return `${BASE}/api/thumbnails/generate?${qs.toString()}`;
  },

  // ---------- Operations / Observability ----------

  // Disk
  opsDisk: () => request<DiskUsage>("/api/ops/disk"),
  opsClearTemp: () =>
    request<{ deleted: number; bytes_freed: number }>("/api/ops/disk/clear-temp", {
      method: "POST",
    }),

  // Cost
  opsCost: (days = 30) => request<CostSummary>(`/api/ops/cost?days=${days}`),
  opsResetCost: () =>
    request<{ ok: boolean }>("/api/ops/cost", { method: "DELETE" }),

  // Errors (upload_failures)
  opsErrors: () => request<ErrorList>("/api/ops/errors"),
  opsErrorFileUrl: (name: string, file: string) =>
    `${BASE}/api/ops/errors/${encodeURIComponent(name)}/file/${encodeURIComponent(file)}`,
  opsDeleteError: (name: string) =>
    request<{ ok: boolean }>(`/api/ops/errors/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),
  opsClearErrors: () =>
    request<{ deleted: number }>("/api/ops/errors/clear", { method: "POST" }),

  // Job log (history)
  opsJobLog: (params: { q?: string; status?: string; channel_id?: string; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.status) qs.set("status", params.status);
    if (params.channel_id) qs.set("channel_id", params.channel_id);
    if (params.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return request<JobLogResponse>(`/api/ops/job-log${q ? "?" + q : ""}`);
  },
  opsJobLogDetail: (id: string) =>
    request<{ job_id: string; content: string }>(
      `/api/ops/job-log/${encodeURIComponent(id)}`,
    ),
  opsClearJobLog: () =>
    request<{ ok: boolean }>("/api/ops/job-log", { method: "DELETE" }),

  // Notifications
  opsGetNotifications: () => request<NotifSettings>("/api/ops/notifications"),
  opsPutNotifications: (payload: NotifSettings) =>
    request<NotifSettings>("/api/ops/notifications", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  opsTestNotifications: () =>
    request<Record<string, { ok: boolean; status?: number; error?: string } | null>>(
      "/api/ops/notifications/test",
      { method: "POST" },
    ),

  // Backup / restore
  opsBackupUrl: (includeVideos = false) =>
    `${BASE}/api/ops/backup?include_videos=${includeVideos}`,
  opsRestore: async (file: File, wipe = false) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${BASE}/api/ops/restore?wipe=${wipe}`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail || JSON.stringify(body);
      } catch {
        // ignore
      }
      throw new Error(`${res.status}: ${detail}`);
    }
    return res.json() as Promise<{ extracted: number; skipped: number; wiped: boolean }>;
  },
};

// ---------- Operations types ----------

export interface DiskUsage {
  total_bytes: number;
  files: number;
  by_ext: Array<{ ext: string; bytes: number; count: number }>;
  biggest: Array<{ path: string; bytes: number; mtime: number }>;
  oldest: { path: string; bytes: number; mtime: number } | null;
  disk_free_bytes: number;
}

export interface CostBucketDay {
  day: string;
  cost_usd: number;
  calls: number;
}
export interface CostBucket {
  cost_usd: number;
  calls: number;
  provider?: string;
  model?: string;
  channel_id?: string;
}
export interface CostSummary {
  total_usd: number;
  total_calls: number;
  by_day: CostBucketDay[];
  by_provider: CostBucket[];
  by_model: CostBucket[];
  by_channel: CostBucket[];
  recent: Array<{
    ts: number;
    provider: string;
    model: string;
    kind: string;
    in_tokens: number;
    out_tokens: number;
    cost_usd: number;
    channel_id?: string;
    note?: string;
  }>;
}

export interface ErrorEntry {
  name: string;
  tag: string;
  ts: number;
  size_bytes: number;
  files: Array<{ name: string; bytes: number }>;
  context: string;
}
export interface ErrorList {
  items: ErrorEntry[];
  total: number;
  by_tag: Array<{ tag: string; count: number }>;
}

export interface JobLogEntry {
  id: string;
  title: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  elapsed: number;
  rc: number | null;
  last_line: string;
  log_lines: number;
  channel_id: string | null;
  kind: string | null;
  ended_ts?: number;
  log_path?: string;
}
export interface JobLogResponse {
  items: JobLogEntry[];
  total: number;
}

export interface NotifSettings {
  discord_webhook_url: string;
  telegram_bot_token: string;
  telegram_chat_id: string;
  on_done: boolean;
  on_error: boolean;
  disk_threshold_gb: number;
}
