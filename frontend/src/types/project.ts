export type Project = {
  id: string;
  title: string;
  description: string | null;
  status: "draft" | "archived" | string;
  storage_bytes: number;
  created_at: string;
  updated_at: string;
  /** Locked at create: export frame; uploads are scaled+padded to this canvas */
  aspect_ratio?: string;
  canvas_width?: number;
  canvas_height?: number;
  slide_count?: number;
  ready_audio_count?: number;
  video_job_count?: number;
  last_render_status?: string | null;
};

export type ProjectSummary = {
  total_projects: number;
  draft_projects: number;
  archived_projects: number;
  total_slides: number;
  ready_audio: number;
  total_video_jobs: number;
  completed_renders: number;
  storage_bytes: number;
};

export type ProjectListResponse = {
  items: Project[];
  total: number;
};
