export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`HTTP ${res.status} on ${path}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export interface SeriesItem {
  id: string;
  name: string;
}

export interface VoiceItem {
  id: string;
  name: string;
  provider?: string;
}

export interface AccountItem {
  id: string;
  platform: string;
  handle: string;
  label?: string;
  nickname?: string;
}

export interface PresetItem {
  id: string;
  name: string;
  config?: Record<string, unknown>;
}

export interface YouTubeVideo {
  id: string;
  title: string;
  thumbnail?: string;
  duration?: string;
}

export type Stage =
  | "topic"
  | "script"
  | "metadata"
  | "prompts"
  | "images"
  | "thumbnail"
  | "tts"
  | "narration"
  | "subtitles"
  | "render"
  | "upload";

export type JobEvent =
  | { type: "queued"; job_id: string; message: string }
  | { type: "running"; message: string }
  | { type: "stage.start"; stage: Stage; message: string }
  | {
      type: "stage.progress";
      stage: Stage;
      current: number;
      total: number;
      percent: number;
      message: string;
      account_id?: string;
    }
  | {
      type: "stage.partial";
      stage: Stage;
      index: number;
      chunk?: string;
      artifact?: string;
    }
  | { type: "stage.done"; stage: Stage; artifacts: Record<string, string>; account_id?: string }
  | { type: "stage.error"; stage: Stage; message: string; account_id?: string }
  // The runner has reached an editable gate and is waiting for the user
  // to POST /api/jobs/{id}/continue. UI should enable the Continue button.
  | { type: "stage.awaiting"; stage: Stage; message: string }
  // The user posted /continue and the runner is unblocked.
  | { type: "stage.resumed"; stage: Stage; message: string }
  | { type: "log"; level: "info" | "warn" | "error"; message: string; account_id?: string }
  | {
      type: "done";
      message: string;
      artifacts: {
        video?: string;
        thumbnail?: string;
        audio?: string;
        metadata?: string;
      };
    }
  | { type: "error"; message: string }
  | { type: "cancelled"; message: string };

export type JobEventHandlers = {
  queued?: (e: Extract<JobEvent, { type: "queued" }>) => void;
  running?: (e: Extract<JobEvent, { type: "running" }>) => void;
  "stage.start"?: (e: Extract<JobEvent, { type: "stage.start" }>) => void;
  "stage.progress"?: (e: Extract<JobEvent, { type: "stage.progress" }>) => void;
  "stage.partial"?: (e: Extract<JobEvent, { type: "stage.partial" }>) => void;
  "stage.done"?: (e: Extract<JobEvent, { type: "stage.done" }>) => void;
  "stage.error"?: (e: Extract<JobEvent, { type: "stage.error" }>) => void;
  "stage.awaiting"?: (e: Extract<JobEvent, { type: "stage.awaiting" }>) => void;
  "stage.resumed"?: (e: Extract<JobEvent, { type: "stage.resumed" }>) => void;
  log?: (e: Extract<JobEvent, { type: "log" }>) => void;
  done?: (e: Extract<JobEvent, { type: "done" }>) => void;
  error?: (e: Extract<JobEvent, { type: "error" }>) => void;
  cancelled?: (e: Extract<JobEvent, { type: "cancelled" }>) => void;
};

export async function getSeries(): Promise<SeriesItem[]> {
  const data = await apiFetch<{ series: SeriesItem[] }>("/api/config/series");
  return data.series;
}

export async function getVoices(): Promise<{
  voices: VoiceItem[];
  default: string;
}> {
  return apiFetch("/api/config/voices");
}

export async function getAccounts(): Promise<AccountItem[]> {
  const data = await apiFetch<{ accounts: AccountItem[] }>("/api/accounts");
  return data.accounts;
}

export async function getPresets(): Promise<PresetItem[]> {
  const data = await apiFetch<{ presets: PresetItem[] }>("/api/presets");
  return data.presets;
}

export async function createPreset(payload: {
  name: string;
  config: Record<string, unknown>;
}): Promise<{ preset: unknown }> {
  return apiFetch("/api/presets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function createJob(payload: {
  type: string;
  topic?: string;
  series_id?: string;
  account_id?: string;
  voice_id?: string;
  image_mode?: string;
  image_style?: string;
  preset_id?: string;
  target_duration?: 60 | 120 | 180;
}): Promise<{ job_id: string }> {
  return apiFetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function cancelJob(
  jobId: string
): Promise<{ cancelled: boolean }> {
  return apiFetch(`/api/jobs/${jobId}/cancel`, { method: "POST" });
}

export async function restartJob(
  jobId: string
): Promise<{ job_id: string }> {
  return apiFetch(`/api/jobs/${jobId}/restart`, { method: "POST" });
}

// Tells the runner thread to advance past the current editable gate. The
// `payload` is applied server-side before the next stage runs (see runners.py
// _apply_script_edits / _apply_metadata_edits / _apply_prompts_edits).
// Task Monitor list view. Polled every 2s by /tasks page. The backend keeps
// summary state per job (current_stage, percent, last_log, awaiting gate)
// so this endpoint is cheap to hit without scanning the SSE event log.
export interface JobSummary {
  job_id: string;
  type: "short" | "long" | "recap";
  topic: string;
  account_id: string;
  status: "queued" | "running" | "uploading" | "done" | "error" | "cancelled" | "unknown";
  current_stage: Stage | null;
  stage_message: string;
  stage_percent: number | null;
  awaiting: Stage | null;
  last_log: string;
  created_at: string | null;
  video_url: string | null;
  has_video: boolean;
  has_thumbnail: boolean;
}

export async function listJobs(): Promise<{ jobs: JobSummary[] }> {
  return apiFetch("/api/jobs");
}

export async function continueJob(
  jobId: string,
  stage: Stage,
  payload: Record<string, unknown> = {}
): Promise<{ resumed: boolean; stage: Stage }> {
  return apiFetch(`/api/jobs/${jobId}/continue`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stage, payload }),
  });
}

// Re-fetch which gate (if any) the runner is currently waiting on. Useful
// when the wizard is mounted late (after the SSE event was already emitted)
// so the Continue button enables itself correctly.
export async function getGateStatus(
  jobId: string
): Promise<{ awaiting: Stage | null }> {
  return apiFetch(`/api/jobs/${jobId}/gate`);
}

export interface JobDetail {
  job_id: string;
  status: string;
  config: Record<string, unknown>;
  artifacts: Record<string, string>;
}

export async function getJob(jobId: string): Promise<JobDetail> {
  return apiFetch(`/api/jobs/${jobId}`);
}

export async function ttsPreview(
  text: string,
  voice_id: string
): Promise<{ path: string; duration_seconds: number }> {
  return apiFetch("/api/tts/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice_id }),
  });
}

export async function triggerUpload(
  jobId: string,
  accountId?: string
): Promise<unknown> {
  return apiFetch(`/api/jobs/${jobId}/upload`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true, ...(accountId ? { account_id: accountId } : {}) }),
  });
}

export async function getJobArtifact(
  jobId: string,
  key: string
): Promise<Response> {
  const url = `${API_BASE}/api/jobs/${jobId}/artifact/${key}`;
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(
      `HTTP ${res.status} on /api/jobs/${jobId}/artifact/${key}: ${text}`
    );
  }
  return res;
}

export async function getYoutubeVideos(
  signal?: AbortSignal
): Promise<{ videos: YouTubeVideo[] }> {
  return apiFetch("/api/youtube/videos", { signal });
}

export function openJobStream(
  jobId: string,
  handlers: JobEventHandlers
): EventSource {
  const es = new EventSource(`${API_BASE}/api/jobs/${jobId}/events`);
  es.onmessage = (event) => {
    let parsed: JobEvent;
    try {
      parsed = JSON.parse(event.data) as JobEvent;
    } catch {
      return;
    }
    const handler = (handlers as Record<string, ((e: JobEvent) => void) | undefined>)[parsed.type];
    if (handler) handler(parsed);
  };
  return es;
}
