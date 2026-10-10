import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { API_BASE, api, getAccessToken, setAccessToken } from "./client";

type SyncVideo = { id: string; status: string };

type SyncMessage = {
  job?: unknown;
  music?: unknown;
  images?: unknown;
  slides?: unknown;
  videos?: SyncVideo[];
  reload_story?: boolean;
};

async function freshToken(): Promise<string | null> {
  const current = getAccessToken();
  if (current) return current;
  try {
    const res = await api.post("/auth/refresh");
    setAccessToken(res.data.access_token);
    return res.data.access_token as string;
  } catch {
    return null;
  }
}

function applySync(qc: ReturnType<typeof useQueryClient>, projectId: string, message: SyncMessage) {
  if (message.job !== undefined || message.music !== undefined || message.images !== undefined) {
    qc.setQueryData(["story", projectId], (current: Record<string, unknown> | undefined) => {
      if (!current) return current;
      return {
        ...current,
        ...(message.job !== undefined ? { job: message.job } : {}),
        ...(message.music !== undefined ? { music: message.music } : {}),
        ...(message.images !== undefined ? { images: message.images } : {}),
      };
    });
  }
  if (message.slides !== undefined) {
    qc.setQueryData(["slides", projectId], message.slides);
    void qc.invalidateQueries({ queryKey: ["export-readiness", projectId] });
  }
  if (message.reload_story) {
    void qc.invalidateQueries({ queryKey: ["story", projectId] });
  }
  for (const video of message.videos || []) {
    const previous = qc.getQueryData(["job", video.id]) as { status?: string } | undefined;
    qc.setQueryData(["job", video.id], (existing: Record<string, unknown> | undefined) =>
      existing ? { ...existing, ...video } : video
    );
    const wasActive = !previous || previous.status === "queued" || previous.status === "processing";
    const finished = video.status === "completed" || video.status === "failed" || video.status === "cancelled";
    if (wasActive && finished) {
      void qc.invalidateQueries({ queryKey: ["videos", projectId] });
    }
  }
}

/** Keep one event stream open for this project instead of polling status endpoints. */
export function useProjectSync(projectId: string) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!projectId) return;
    const controller = new AbortController();
    let stopped = false;
    let retryMs = 1000;

    const run = async () => {
      while (!stopped) {
        const token = await freshToken();
        if (stopped) return;
        if (!token) {
          await new Promise((resolve) => window.setTimeout(resolve, retryMs));
          retryMs = Math.min(retryMs * 2, 10000);
          continue;
        }
        try {
          const response = await fetch(`${API_BASE}/projects/${projectId}/events`, {
            headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
            signal: controller.signal,
          });
          if (response.status === 401) {
            setAccessToken(null);
            continue;
          }
          if (!response.ok || !response.body) {
            throw new Error(`Event stream failed (${response.status})`);
          }
          retryMs = 1000;
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          while (!stopped) {
            const chunk = await reader.read();
            if (chunk.done) break;
            buffer += decoder.decode(chunk.value, { stream: true });
            const frames = buffer.split("\n\n");
            buffer = frames.pop() || "";
            for (const frame of frames) {
              const data = frame
                .split("\n")
                .filter((line) => line.startsWith("data:"))
                .map((line) => line.slice(5).trim())
                .join("\n");
              if (!data) continue;
              applySync(qc, projectId, JSON.parse(data) as SyncMessage);
            }
          }
        } catch (error) {
          if (stopped || controller.signal.aborted) return;
          if (error instanceof Error && error.name === "AbortError") return;
        }
        if (stopped) return;
        await new Promise((resolve) => window.setTimeout(resolve, retryMs));
        retryMs = Math.min(retryMs * 2, 10000);
      }
    };

    void run();
    return () => {
      stopped = true;
      controller.abort();
    };
  }, [projectId, qc]);
}
