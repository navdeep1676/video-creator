export type ProgressCopy = {
  title: string;
  detail: string;
  phase: string;
};

export const RENDER_PHASES = [
  { id: "check", label: "Check" },
  { id: "scenes", label: "Scenes" },
  { id: "join", label: "Join" },
  { id: "audio", label: "Audio" },
  { id: "combine", label: "Combine" },
  { id: "finish", label: "Finish" },
];

const RENDER_STAGES: Record<string, ProgressCopy> = {
  validate: {
    title: "Checking slides and audio",
    detail: "Making sure every scene can render.",
    phase: "check",
  },
  queued: {
    title: "Waiting for the render worker",
    detail: "The job is in the queue.",
    phase: "check",
  },
  segments: {
    title: "Building scene clips",
    detail: "Each scene becomes a short video.",
    phase: "scenes",
  },
  concat_video: {
    title: "Joining the scenes",
    detail: "Stitching the clips into one picture track.",
    phase: "join",
  },
  audio: {
    title: "Preparing narration",
    detail: "Lining up each voice with its scene.",
    phase: "audio",
  },
  audio_mix: {
    title: "Mixing the music",
    detail: "Placing the score under the narration.",
    phase: "audio",
  },
  subtitles: {
    title: "Writing captions",
    detail: "Building the caption file.",
    phase: "combine",
  },
  mux: {
    title: "Combining picture and sound",
    detail: "Encoding the final video. This step can sit on one percent while FFmpeg works.",
    phase: "combine",
  },
  thumbnail: {
    title: "Making the thumbnail",
    detail: "Grabbing a preview frame.",
    phase: "finish",
  },
  finalize: {
    title: "Finishing the file",
    detail: "Saving the video.",
    phase: "finish",
  },
  cancelled: {
    title: "Render stopped",
    detail: "",
    phase: "check",
  },
};

export function describeRender(stage: string | null, status: string): ProgressCopy {
  const raw = (stage || "").trim();
  if (status === "completed") {
    return { title: "Render finished", detail: "The video is ready to play.", phase: "finish" };
  }
  if (!raw && status === "queued") return RENDER_STAGES.queued;
  const wan = raw.match(/^wan\s+(\d+)\s*\/\s*(\d+)(?:\s+(.*))?$/i);
  if (wan) {
    const extra = (wan[3] || "").trim();
    const step = extra.match(/^step\s+(\d+)\s*\/\s*(\d+)$/i);
    let detail = "Wan 2.2 is making this scene.";
    if (step) detail = `Diffusion step ${step[1]} of ${step[2]}.`;
    else if (/loading/i.test(extra)) detail = "Loading the Wan model into memory. The first load is the slow part.";
    else if (/sampling/i.test(extra)) detail = "Starting diffusion sampling.";
    else if (/export/i.test(extra)) detail = "Saving the clip.";
    else if (/cached/i.test(extra)) detail = "Using a clip that was already generated.";
    else if (/start/i.test(extra)) detail = "Starting this scene.";
    else if (extra) detail = extra;
    return {
      title: `AI motion, scene ${wan[1]} of ${wan[2]}`,
      detail,
      phase: "scenes",
    };
  }
  const legacy = raw.match(/^wan_ti2v:?\s*(.*)$/i);
  if (legacy) {
    return {
      title: "Generating AI motion",
      detail: legacy[1] || "Wan 2.2 is making this clip.",
      phase: "scenes",
    };
  }
  const scene = raw.match(/^scene\s+(\d+)\s*\/\s*(\d+)$/i);
  if (scene) {
    return {
      title: `Building scene ${scene[1]} of ${scene[2]}`,
      detail: "Fitting the picture to the frame.",
      phase: "scenes",
    };
  }
  if (RENDER_STAGES[raw]) return RENDER_STAGES[raw];
  if (status === "processing" || status === "running") {
    return { title: "Rendering", detail: raw, phase: "scenes" };
  }
  return { title: raw || status, detail: "", phase: "check" };
}

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remain = total % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return remain ? `${minutes}m ${remain}s` : `${minutes}m`;
  return `${remain}s`;
}

export function elapsedSeconds(
  startedAt: string | null | undefined,
  createdAt: string | null | undefined,
  now: number,
  finishedAt?: string | null
): number | null {
  const start = Date.parse(startedAt || createdAt || "");
  if (Number.isNaN(start)) return null;
  const end = finishedAt ? Date.parse(finishedAt) : now;
  if (Number.isNaN(end)) return null;
  return Math.max(0, (end - start) / 1000);
}

/** Rough time left from elapsed time and the current percent. Hidden until the bar has actually moved. */
export function etaSeconds(elapsed: number | null, progress: number, active: boolean): number | null {
  if (!active || elapsed == null || elapsed < 8 || progress < 8 || progress >= 100) return null;
  const remaining = (elapsed * (100 - progress)) / progress;
  if (!Number.isFinite(remaining) || remaining < 0) return null;
  return remaining;
}
