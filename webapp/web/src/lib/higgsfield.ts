/** Higgsfield Studio API client */

const BASE = "/api/higgsfield";

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...opts?.headers },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export interface HFProject {
  id: string;
  version: number;
  title: string;
  topic: string;
  phase: string;
  progress: number;
  created_at: number;
  updated_at: number;
  job_id: string;
  error: string;
}

export interface NewProductionInput {
  title?: string;
  topic: string;
  target_duration_min?: number;
  aspect_ratio?: string;
  resolution?: string;
  language?: string;
  narrator_voice?: string;
  style?: string;
  genre?: string;
  quality?: string;
  provider?: string;
  research_mode?: string;
  director_mode?: string;
  production_mode?: string;
  budget_limit?: number | null;
  dry_run?: boolean;
  channel_id?: string;
  series_id?: string;
}

export interface Shot {
  id: string;
  scene_id: string;
  sequence: number;
  duration_sec: number;
  shot_type: string;
  subject: string;
  action: string;
  prompt: string;
  optimized_prompt: string;
  negative_prompt: string;
  prompt_quality_score: number;
  model_id: string;
  status: string;
  selected_version: number;
  versions: any[];
  importance: number;
  estimated_cost: number | null;
  actual_cost: number | null;
  emotion: string;
  camera: string;
  lighting: string;
  environment: string;
  composition: string;
  transition: string;
  regeneration_count: number;
}

export const hfApi = {
  listProjects: () => request<HFProject[]>("/projects"),
  createProject: (data: NewProductionInput) =>
    request<{ id: string; phase: string }>("/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getProject: (id: string) => request<any>(`/projects/${id}`),
  deleteProject: (id: string) =>
    request<any>(`/projects/${id}`, { method: "DELETE" }),

  getScript: (id: string) => request<any>(`/projects/${id}/script`),
  getStoryboard: (id: string) => request<any>(`/projects/${id}/storyboard`),
  getShots: (id: string) => request<any>(`/projects/${id}/shots`),
  getVisualBible: (id: string) => request<any>(`/projects/${id}/visual-bible`),
  getTimeline: (id: string) => request<any>(`/projects/${id}/timeline`),
  getCost: (id: string) => request<any>(`/projects/${id}/cost`),
  getRhythm: (id: string) => request<any>(`/projects/${id}/rhythm`),
  getManifest: (id: string) => request<any>(`/projects/${id}/manifest`),
  getVersions: (id: string) => request<any[]>(`/projects/${id}/versions`),

  updateBudget: (id: string, budget_limit: number) =>
    request<any>(`/projects/${id}/budget`, {
      method: "PUT",
      body: JSON.stringify({ budget_limit }),
    }),

  shotAction: (projectId: string, shotId: string, action: string, prompt?: string, model_id?: string) =>
    request<any>(`/projects/${projectId}/shots/${shotId}`, {
      method: "POST",
      body: JSON.stringify({ action, prompt, model_id }),
    }),

  cancelProduction: (id: string) =>
    request<any>(`/projects/${id}/cancel`, { method: "POST" }),

  runProductionUrl: (id: string) => `${BASE}/projects/${id}/run`,

  listProviders: () => request<{ providers: string[] }>("/providers"),
  listModels: (provider: string) => request<any>(`/providers/${provider}/models`),
  listGenres: () => request<{ genres: string[] }>("/genres"),
};
