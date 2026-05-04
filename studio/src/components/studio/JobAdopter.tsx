"use client";

// JobAdopter — invisible component that reads `?job=<id>` from the URL,
// fetches the job's current state from the backend, and hydrates the
// production store so the wizard can render the correct stage.
//
// Used by `/shorts` and `/long` routes. Mounted by ProductionCanvas
// when `type === "short" | "long"`.
//
// Behavior:
//   - If ?job= is missing → no-op.
//   - If the job is unknown to the backend → no-op (let the user see the
//     normal "New Production" CTA instead of a confusing error).
//   - If the job is known → adopt it into the local store and jump to
//     the stage matching the awaiting gate (or the last completed stage).

import { useEffect, useRef } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  apiFetch,
  getGateStatus,
  type JobSummary,
  type Stage,
} from "@/lib/api";
import { useProductionStore } from "@/stores/production";

// Order must match SHORT_STAGES / long stages in ProductionCanvas:
// [0] config, [1] script, [2] images, [3] thumbnail, [4] narration, [5] render, [6] upload
const STAGE_TO_STEP: Record<string, number> = {
  topic: 1,
  script: 1,
  metadata: 1,
  prompts: 2,
  images: 2,
  thumbnail: 3,
  narration: 4,
  tts: 4,
  render: 5,
  upload: 6,
};

interface JobDetails {
  job_id: string;
  status: JobSummary["status"];
  config: Record<string, unknown>;
  artifacts: Record<string, string>;
}

export function JobAdopter({ type }: { type: "short" | "long" }) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const adoptedRef = useRef<string | null>(null);

  const jobId = searchParams.get("job");

  useEffect(() => {
    if (!jobId) return;
    if (adoptedRef.current === jobId) return; // already done in this mount
    adoptedRef.current = jobId;

    let cancelled = false;

    (async () => {
      try {
        // Fetch the job + its open gate in parallel.
        const [job, gate] = await Promise.all([
          apiFetch<JobDetails>(`/api/jobs/${jobId}`),
          getGateStatus(jobId).catch(() => ({ awaiting: null as Stage | null })),
        ]);

        if (cancelled) return;

        const cfg = job.config || {};
        const artifacts = job.artifacts || {};

        // Try to load the script text artifact so the ScriptStage textarea
        // is pre-populated with what the LLM produced (otherwise the user
        // would just see "Generating script…" until the next SSE event).
        let scriptText: string | undefined;
        try {
          if (artifacts.script) {
            const r = await apiFetch<{ script: string; sections: string[] }>(
              `/api/jobs/${jobId}/artifact/script`
            );
            scriptText = r.script;
          }
        } catch {
          // not fatal
        }

        // Same for prompts.
        let imagePrompts: string[] | undefined;
        try {
          if (artifacts.prompts) {
            const r = await apiFetch<{ prompts: string[] } | string[]>(
              `/api/jobs/${jobId}/artifact/prompts`
            );
            imagePrompts = Array.isArray(r) ? r : r.prompts;
          }
        } catch {
          // not fatal
        }

        // Decide which step to land on.
        const awaiting = gate.awaiting;
        let initialStep: number;
        if (awaiting) {
          initialStep = STAGE_TO_STEP[awaiting] ?? 1;
        } else if (job.status === "done") {
          initialStep = 6; // upload
        } else if (artifacts.video) {
          initialStep = 6;
        } else if (artifacts.audio) {
          initialStep = 5;
        } else if (artifacts.thumbnail) {
          initialStep = 4;
        } else if (artifacts.prompts) {
          initialStep = 2;
        } else if (artifacts.script) {
          initialStep = 1;
        } else {
          initialStep = 1;
        }

        useProductionStore.getState().adoptJob(
          type,
          jobId,
          {
            topic: String(cfg.topic ?? ""),
            accountId: cfg.account_id ? String(cfg.account_id) : undefined,
            voiceId: cfg.voice_id ? String(cfg.voice_id) : undefined,
            imageMode: (cfg.image_mode === "photos" ? "photos" : "ai"),
            imageStyle: cfg.image_style ? String(cfg.image_style) : undefined,
            seriesId: cfg.series_id ? String(cfg.series_id) : undefined,
            script: scriptText,
            imagePrompts,
            videoPath: artifacts.video,
          },
          initialStep
        );

        // Strip ?job= from the URL after adoption so refreshing the
        // wizard doesn't re-trigger this and clobber the user's edits.
        const sp = new URLSearchParams(searchParams.toString());
        sp.delete("job");
        const qs = sp.toString();
        router.replace(qs ? `?${qs}` : "?", { scroll: false });
      } catch {
        // Job not found or backend down → silently fall back to the
        // normal "New Production" CTA.
      }
    })();

    return () => {
      cancelled = true;
    };
    // adoptedRef guard prevents double-adoption; deps intentionally tight.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, type]);

  return null;
}
