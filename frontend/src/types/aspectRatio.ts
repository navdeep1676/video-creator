export type AspectRatioId = "16:9" | "9:16" | "1:1" | "4:5";

export type AspectRatioOption = {
  id: AspectRatioId;
  label: string;
  description: string;
  width: number;
  height: number;
  category: string;
};

export const ASPECT_RATIO_OPTIONS: AspectRatioOption[] = [
  {
    id: "16:9",
    label: "Landscape 16:9",
    description: "YouTube, courses, desktop long-form",
    width: 1920,
    height: 1080,
    category: "long",
  },
  {
    id: "9:16",
    label: "Portrait 9:16",
    description: "YouTube Shorts, TikTok, Instagram Reels",
    width: 1080,
    height: 1920,
    category: "short",
  },
  {
    id: "1:1",
    label: "Square 1:1",
    description: "Instagram feed, carousel posts",
    width: 1080,
    height: 1080,
    category: "square",
  },
  {
    id: "4:5",
    label: "Vertical 4:5",
    description: "Instagram portrait feed",
    width: 1080,
    height: 1350,
    category: "social",
  },
];

export const DEFAULT_ASPECT_RATIO: AspectRatioId = "16:9";

/** Relative tolerance matching backend ASPECT_RATIO_TOLERANCE */
export const ASPECT_RATIO_TOLERANCE = 0.04;

export function getAspectOption(id: string | null | undefined): AspectRatioOption {
  return ASPECT_RATIO_OPTIONS.find((r) => r.id === id) || ASPECT_RATIO_OPTIONS[0];
}

export function imageMatchesAspect(
  width: number,
  height: number,
  aspectId: string,
  tolerance = ASPECT_RATIO_TOLERANCE,
): boolean {
  if (width <= 0 || height <= 0) return false;
  const preset = getAspectOption(aspectId);
  const actual = width / height;
  const expected = preset.width / preset.height;
  return Math.abs(actual - expected) / expected <= tolerance;
}

export function loadImageSize(file: File): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error(`Could not read image: ${file.name}`));
    };
    img.src = url;
  });
}

export async function filterFilesByAspect(
  files: File[],
  aspectId: string,
): Promise<{ ok: File[]; rejected: { name: string; width: number; height: number }[] }> {
  const ok: File[] = [];
  const rejected: { name: string; width: number; height: number }[] = [];
  for (const f of files) {
    try {
      const { width, height } = await loadImageSize(f);
      if (imageMatchesAspect(width, height, aspectId)) {
        ok.push(f);
      } else {
        rejected.push({ name: f.name, width, height });
      }
    } catch {
      rejected.push({ name: f.name, width: 0, height: 0 });
    }
  }
  return { ok, rejected };
}
