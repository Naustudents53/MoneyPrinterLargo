"use client";

import { useEffect } from "react";
import { openJobStream, type JobEventHandlers } from "@/lib/api";

export function useJobEvents(
  jobId: string | null,
  handlers: JobEventHandlers
) {
  useEffect(() => {
    if (!jobId) return;
    const es = openJobStream(jobId, handlers);
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);
}
