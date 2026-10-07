import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import AddPhotoAlternateIcon from "@mui/icons-material/AddPhotoAlternate";
import NoteAddIcon from "@mui/icons-material/NoteAdd";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";
import MovieCreationIcon from "@mui/icons-material/MovieCreation";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import StopIcon from "@mui/icons-material/Stop";
import VisibilityIcon from "@mui/icons-material/Visibility";
import CloseIcon from "@mui/icons-material/Close";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { api, errMessage, mediaUrl } from "../api/client";
import SlideList from "../components/SlideList";
import PageHeader from "../components/PageHeader";
import ProjectFormDialog, { type ProjectFormValues } from "../components/ProjectFormDialog";
import StoryPanel from "../components/StoryPanel";
import ConfirmDialog from "../components/ConfirmDialog";
import type { Project } from "../types/project";
import { getAspectOption } from "../types/aspectRatio";

type Narration = {
  id: string;
  text: string;
  voice: string;
  speed: number;
  audio_url: string | null;
  tts_status: string;
  tts_error: string | null;
  audio_duration_ms: number | null;
};

type SlideImage = {
  index: number;
  image_key: string;
  image_url: string | null;
  duration_ms?: number | null;
};

type Slide = {
  id: string;
  order_index: number;
  image_url: string | null;
  images?: SlideImage[];
  image_count?: number;
  duration_ms: number;
  effective_duration_ms: number;
  transition: string;
  animation: string;
  /** Motion or text prompt for Wan2.1 I2V / T2V */
  motion_prompt?: string | null;
  narration: Narration | null;
};

type Voice = {
  id: string;
  name: string;
  language: string;
  language_label?: string;
  gender: string;
  accent?: string;
  provider?: string;
  providers?: string[];
  runtime_provider?: string;
  requires_deepgram_key?: boolean;
};

type Language = { code: string; label: string };

type TtsProvidersStatus = {
  deepgram_available: boolean;
  edge_available: boolean;
  providers: { id: string; label: string; available: boolean; description: string }[];
};

type Draft = {
  slideId: string;
  text: string;
  voice: string;
  speed: number;
  transition: string;
  animation: string;
  motion_prompt: string;
};

function draftFromSlide(slide: Slide): Draft {
  return {
    slideId: slide.id,
    text: slide.narration?.text || "",
    voice: slide.narration?.voice || "edge-en-ava",
    speed: slide.narration?.speed ?? 1,
    transition: slide.transition || "fade",
    animation: slide.animation || "none",
    motion_prompt: slide.motion_prompt || "",
  };
}

function languageForVoice(voiceId: string, voices: Voice[]): string {
  return voices.find((v) => v.id === voiceId)?.language || "en";
}

type WanI2vStatus = {
  enabled: boolean;
  backend: string;
  mock: boolean;
  real_ai?: boolean;
  fal_configured?: boolean;
  replicate_configured?: boolean;
  ready: boolean;
  error?: string | null;
  hint?: string | null;
};

function WanT2vBanner() {
  const { data } = useQuery({
    queryKey: ["wan-t2v-status"],
    queryFn: async () => (await api.get("/video/wan-t2v/status")).data as WanI2vStatus,
    staleTime: 30_000,
  });
  if (!data) return null;
  if (data.real_ai) {
    return (
      <Alert severity="success" variant="outlined">
        Wan2.1 T2V 1.3B runs locally via <strong>{data.backend}</strong>. ComfyUI is not used.
        Export writes a 480p clip from the prompt. The first run downloads the weights.
      </Alert>
    );
  }
  if (data.mock) {
    return (
      <Alert severity="warning" variant="outlined">
        <strong>Mock mode</strong> — this is a solid-color stand-in, not Wan2.1. Set{" "}
        <code>WAN_T2V_MOCK=false</code> and install the local 1.3B weights.
      </Alert>
    );
  }
  return (
    <Alert severity="error" variant="outlined">
      Wan2.1 T2V 1.3B is not ready. {data.error || data.hint || "Install the local model."} This
      path does not use ComfyUI.
    </Alert>
  );
}

function isDraftDirty(draft: Draft, slide: Slide | null | undefined): boolean {
  if (!slide || draft.slideId !== slide.id) return false;
  const base = draftFromSlide(slide);
  return (
    draft.text !== base.text ||
    draft.voice !== base.voice ||
    draft.speed !== base.speed ||
    draft.transition !== base.transition ||
    draft.animation !== base.animation ||
    draft.motion_prompt !== base.motion_prompt
  );
}

export default function ProjectPage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Slide | null>(null);
  const [deleteProjectOpen, setDeleteProjectOpen] = useState(false);
  const [editProjectOpen, setEditProjectOpen] = useState(false);
  const [projectFormError, setProjectFormError] = useState("");
  /** Index into selected.images for full-size view of the fitted/export image */
  const [viewImageIndex, setViewImageIndex] = useState<number | null>(null);
  const draftRef = useRef<Draft | null>(null);
  const slidesRef = useRef<Slide[]>([]);
  const savingRef = useRef(false);

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    setViewImageIndex(null);
  }, [selectedId]);

  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: async () => (await api.get(`/projects/${projectId}`)).data as Project,
  });
  const projectAspect = getAspectOption(projectQuery.data?.aspect_ratio);

  const updateProjectMutation = useMutation({
    mutationFn: async (values: ProjectFormValues) => {
      const { data } = await api.patch(`/projects/${projectId}`, {
        title: values.title,
        description: values.description || null,
        status: values.status,
        aspect_ratio: values.aspect_ratio,
      });
      return data as Project;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project", projectId] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["projects-summary"] });
      setEditProjectOpen(false);
      setSuccess("Project updated");
    },
    onError: (e) => setProjectFormError(errMessage(e)),
  });

  const deleteProjectMutation = useMutation({
    mutationFn: async () => {
      await api.delete(`/projects/${projectId}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["projects-summary"] });
      navigate("/projects");
    },
    onError: (e) => setError(errMessage(e)),
  });

  const slidesQuery = useQuery({
    queryKey: ["slides", projectId],
    queryFn: async () => (await api.get(`/projects/${projectId}/slides`)).data as Slide[],
    refetchInterval: (query) => {
      const data = query.state.data as Slide[] | undefined;
      if (!data) return false;
      const busy = data.some((s) => ["queued", "processing"].includes(s.narration?.tts_status || ""));
      return busy ? 2000 : false;
    },
  });

  const languagesQuery = useQuery({
    queryKey: ["languages"],
    queryFn: async () => (await api.get("/tts/languages")).data as Language[],
  });

  const providersQuery = useQuery({
    queryKey: ["tts-providers"],
    queryFn: async () => (await api.get("/tts/providers")).data as TtsProvidersStatus,
  });

  const voicesQuery = useQuery({
    queryKey: ["voices"],
    queryFn: async () => (await api.get("/tts/voices")).data as Voice[],
  });

  const allVoices = voicesQuery.data || [];
  const languages = languagesQuery.data || [];
  const deepgramAvailable = providersQuery.data?.deepgram_available ?? false;

  const [languageFilter, setLanguageFilter] = useState<string>("en");
  // all | deepgram | edge — default Edge free TTS
  const [engineFilter, setEngineFilter] = useState<string>("edge");

  // Keep language/engine filters in sync with selected slide voice
  useEffect(() => {
    if (!draft || allVoices.length === 0) return;
    const lang = languageForVoice(draft.voice, allVoices);
    setLanguageFilter(lang);
    const v = allVoices.find((x) => x.id === draft.voice);
    if (v?.provider === "deepgram") setEngineFilter("deepgram");
    else if (v?.provider === "edge") setEngineFilter("edge");
  }, [draft?.slideId, draft?.voice, allVoices]);

  const voicesForLanguage = useMemo(() => {
    let list = allVoices.filter((v) => v.language === languageFilter);
    if (engineFilter === "deepgram") {
      list = list.filter((v) => (v.providers || []).includes("deepgram") || v.provider === "deepgram");
    } else if (engineFilter === "edge") {
      list = list.filter((v) => v.provider === "edge");
    }
    return list;
  }, [allVoices, languageFilter, engineFilter]);

  const slides = slidesQuery.data || [];
  slidesRef.current = slides;

  const selected = useMemo(
    () => slides.find((s) => s.id === selectedId) || null,
    [slides, selectedId]
  );

  // Initial selection
  useEffect(() => {
    if (!selectedId && slides[0]) {
      setSelectedId(slides[0].id);
    } else if (selectedId && slides.length > 0 && !slides.some((s) => s.id === selectedId)) {
      // Selected slide deleted
      setSelectedId(slides[0]?.id ?? null);
    }
  }, [slides, selectedId]);

  // Load draft when selected slide changes (not on every poll refresh)
  useEffect(() => {
    if (!selected) {
      setDraft(null);
      return;
    }
    setDraft((prev) => {
      // Keep in-progress edits for the same slide across background refetches
      if (prev && prev.slideId === selected.id && isDraftDirty(prev, selected)) {
        return prev;
      }
      return draftFromSlide(selected);
    });
  }, [selected?.id]);

  // When server data updates for the current slide and user is not dirty, refresh draft
  useEffect(() => {
    if (!selected || !draft) return;
    if (draft.slideId !== selected.id) return;
    if (isDraftDirty(draft, selected)) return;
    const next = draftFromSlide(selected);
    // Avoid loop: only update if something meaningful changed (e.g. tts finished doesn't change draft fields)
    if (
      next.text !== draft.text ||
      next.voice !== draft.voice ||
      next.speed !== draft.speed ||
      next.transition !== draft.transition ||
      next.animation !== draft.animation ||
      next.motion_prompt !== draft.motion_prompt
    ) {
      setDraft(next);
    }
  }, [selected, draft]);

  const persistSlide = useCallback(
    async (payload: Draft) => {
      await api.patch(`/slides/${payload.slideId}`, {
        text: payload.text,
        voice: payload.voice,
        speed: payload.speed,
        transition: payload.transition,
        animation: payload.animation,
        motion_prompt: payload.motion_prompt,
      });
    },
    []
  );

  const saveDraftIfNeeded = useCallback(
    async (d: Draft | null) => {
      if (!d || savingRef.current) return;
      const slide = slidesRef.current.find((s) => s.id === d.slideId);
      if (!slide || !isDraftDirty(d, slide)) return;
      savingRef.current = true;
      try {
        await persistSlide(d);
        await qc.invalidateQueries({ queryKey: ["slides", projectId] });
      } finally {
        savingRef.current = false;
      }
    },
    [persistSlide, projectId, qc]
  );

  const selectSlide = useCallback(
    async (nextId: string) => {
      if (nextId === selectedId) return;
      const current = draftRef.current;
      // Auto-save previous slide before switching so narration never sticks to the wrong image
      try {
        await saveDraftIfNeeded(current);
      } catch (e) {
        setError(errMessage(e));
        return; // stay on current slide if save failed
      }
      setSelectedId(nextId);
    },
    [selectedId, saveDraftIfNeeded]
  );

  const saveSlide = useMutation({
    mutationFn: async () => {
      const d = draftRef.current;
      if (!d) return;
      await persistSlide(d);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["slides", projectId] });
      setSuccess("Slide saved");
    },
    onError: (e) => setError(errMessage(e)),
  });

  function prepareImages(fileList: File[]): File[] {
    if (!fileList.length) throw new Error("No files selected");
    // Server scales + pads to project canvas (no crop; full image kept)
    const allowed = new Set(["image/png", "image/jpeg", "image/jpg", "image/webp"]);
    const ok = fileList.filter(
      (f) => allowed.has(f.type.toLowerCase()) || /\.(png|jpe?g|webp)$/i.test(f.name),
    );
    if (!ok.length) throw new Error("Use PNG, JPEG, or WebP images");
    return ok;
  }

  const createSlideMutation = useMutation({
    mutationFn: async () => {
      await saveDraftIfNeeded(draftRef.current);
      const { data } = await api.post(`/projects/${projectId}/slides/create`, {});
      return data as Slide;
    },
    onSuccess: (slide) => {
      qc.invalidateQueries({ queryKey: ["slides", projectId] });
      qc.invalidateQueries({ queryKey: ["project", projectId] });
      setSelectedId(slide.id);
      setSuccess("Slide created — add images to it");
    },
    onError: (e) => setError(errMessage(e)),
  });

  /** Each file becomes its own slide */
  const uploadAsSlidesMutation = useMutation({
    mutationFn: async (fileList: File[]) => {
      const ok = prepareImages(fileList);
      await saveDraftIfNeeded(draftRef.current);
      const form = new FormData();
      ok.forEach((f) => form.append("files", f));
      await api.post(`/projects/${projectId}/slides`, form);
      return ok.length;
    },
    onSuccess: (count) => {
      qc.invalidateQueries({ queryKey: ["slides", projectId] });
      qc.invalidateQueries({ queryKey: ["project", projectId] });
      const ar = projectAspect.id;
      setSuccess(
        `${count} new slide${count === 1 ? "" : "s"} created · resized to ${ar}`,
      );
    },
    onError: (e) => setError(errMessage(e)),
  });

  /** Add images onto the currently selected slide */
  const addImagesMutation = useMutation({
    mutationFn: async (fileList: File[]) => {
      if (!selectedId) throw new Error("Select a slide first");
      const ok = prepareImages(fileList);
      await saveDraftIfNeeded(draftRef.current);
      const form = new FormData();
      ok.forEach((f) => form.append("files", f));
      const { data } = await api.post(`/slides/${selectedId}/images`, form);
      return data as Slide;
    },
    onSuccess: (slide) => {
      qc.invalidateQueries({ queryKey: ["slides", projectId] });
      setSuccess(
        `Added images · slide now has ${slide.image_count ?? 0} · resized to ${projectAspect.id}`,
      );
    },
    onError: (e) => setError(errMessage(e)),
  });

  const removeImageMutation = useMutation({
    mutationFn: async (imageIndex: number) => {
      if (!selectedId) throw new Error("No slide selected");
      const { data } = await api.delete(`/slides/${selectedId}/images/${imageIndex}`);
      return data as Slide;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["slides", projectId] });
      setSuccess("Image removed from slide");
    },
    onError: (e) => setError(errMessage(e)),
  });

  const updateImageDurationMutation = useMutation({
    mutationFn: async ({ index, durationMs }: { index: number; durationMs: number }) => {
      if (!selectedId) throw new Error("No slide selected");
      const { data } = await api.patch(`/slides/${selectedId}/images/${index}`, {
        duration_ms: durationMs,
      });
      return data as Slide;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["slides", projectId] });
    },
    onError: (e) => setError(errMessage(e)),
  });

  const distributeDurationsMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) throw new Error("No slide selected");
      const { data } = await api.post(`/slides/${selectedId}/images/distribute`);
      return data as Slide;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["slides", projectId] });
      setSuccess("Image times split evenly across the slide");
    },
    onError: (e) => setError(errMessage(e)),
  });

  const ttsOne = useMutation({
    mutationFn: async (force: boolean) => {
      const d = draftRef.current;
      if (!d) return;
      // Always pin to draft.slideId (not "selected") so a mid-click switch can't mis-associate
      await persistSlide(d);
      await api.post("/tts/generate", { slide_id: d.slideId, force });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["slides", projectId] });
      setSuccess("Voice generation queued");
    },
    onError: (e) => setError(errMessage(e)),
  });

  const ttsBatch = useMutation({
    mutationFn: async () => {
      await saveDraftIfNeeded(draftRef.current);
      await api.post("/tts/generate-batch", { project_id: projectId, force: false });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["slides", projectId] });
      setSuccess("Batch voice generation queued");
    },
    onError: (e) => setError(errMessage(e)),
  });

  const applyLanguageMutation = useMutation({
    mutationFn: async (payload: { language: string; voice: string; regenerate: boolean }) => {
      await saveDraftIfNeeded(draftRef.current);
      return (
        await api.post("/tts/apply-language", {
          project_id: projectId,
          language: payload.language,
          voice: payload.voice,
          regenerate: payload.regenerate,
        })
      ).data as { updated: number; enqueued: number; language: string; voice: string };
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["slides", projectId] });
      qc.invalidateQueries({ queryKey: ["project", projectId] });
      setSuccess(
        data.enqueued > 0
          ? `Applied ${data.language} voice to ${data.updated} slides · regenerating ${data.enqueued}`
          : `Applied language voice to ${data.updated} slides`
      );
      // Keep editor draft voice in sync
      setDraft((d) => (d ? { ...d, voice: data.voice } : d));
      setLanguageFilter(data.language);
    },
    onError: (e) => setError(errMessage(e)),
  });

  const reorderMutation = useMutation({
    mutationFn: async (slideIds: string[]) => {
      await saveDraftIfNeeded(draftRef.current);
      const { data } = await api.post(`/projects/${projectId}/slides/reorder`, {
        slide_ids: slideIds,
      });
      return data as Slide[];
    },
    onMutate: async (slideIds) => {
      await qc.cancelQueries({ queryKey: ["slides", projectId] });
      const prev = qc.getQueryData<Slide[]>(["slides", projectId]);
      if (prev) {
        const byId = new Map(prev.map((s) => [s.id, s]));
        const optimistic = slideIds
          .map((id, order_index) => {
            const s = byId.get(id);
            return s ? { ...s, order_index } : null;
          })
          .filter(Boolean) as Slide[];
        qc.setQueryData(["slides", projectId], optimistic);
      }
      return { prev };
    },
    onError: (e, _ids, ctx) => {
      if (ctx?.prev) qc.setQueryData(["slides", projectId], ctx.prev);
      setError(errMessage(e));
    },
    onSuccess: (data) => {
      qc.setQueryData(["slides", projectId], data);
      setSuccess("Slides reordered");
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["slides", projectId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (slideId: string) => {
      // If deleting another slide, still save current draft first
      if (draftRef.current && draftRef.current.slideId !== slideId) {
        await saveDraftIfNeeded(draftRef.current);
      }
      await api.delete(`/slides/${slideId}`);
      return slideId;
    },
    onSuccess: (slideId) => {
      setDeleteTarget(null);
      if (selectedId === slideId) {
        const remaining = slidesRef.current.filter((s) => s.id !== slideId);
        setSelectedId(remaining[0]?.id ?? null);
        setDraft(null);
      }
      qc.invalidateQueries({ queryKey: ["slides", projectId] });
      setSuccess("Slide deleted");
    },
    onError: (e) => setError(errMessage(e)),
  });

  const moveSlide = useCallback(
    (id: string, direction: "up" | "down") => {
      const ids = slides.map((s) => s.id);
      const idx = ids.indexOf(id);
      if (idx < 0) return;
      const swap = direction === "up" ? idx - 1 : idx + 1;
      if (swap < 0 || swap >= ids.length) return;
      const next = [...ids];
      [next[idx], next[swap]] = [next[swap], next[idx]];
      reorderMutation.mutate(next);
    },
    [slides, reorderMutation]
  );

  const readyCount = slides.filter((s) => s.narration?.tts_status === "ready").length;
  const busyTtsCount = slides.filter((s) =>
    ["queued", "processing"].includes(s.narration?.tts_status || "")
  ).length;
  const totalDuration = slides.reduce((a, s) => a + s.effective_duration_ms, 0);
  const dirty = selected ? isDraftDirty(draft ?? draftFromSlide(selected), selected) : false;

  const stopJobsMutation = useMutation({
    mutationFn: async () => {
      // Stop TTS + any active renders for this project
      const { data } = await api.post(`/video/projects/${projectId}/stop`);
      return data as { cancelled_tts: number; cancelled_renders: number; revoked_tasks: number };
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["slides", projectId] });
      setSuccess(
        `Stopped processes · TTS: ${data.cancelled_tts} · renders: ${data.cancelled_renders}`
      );
    },
    onError: (e) => setError(errMessage(e)),
  });

  // Only show editor when draft is for the currently selected slide
  const editorReady = selected && draft && draft.slideId === selected.id;

  return (
    <Stack spacing={3}>
      <PageHeader
        title={projectQuery.data?.title || "Project"}
        subtitle={`${projectAspect.id} · ${slides.length} slides · ${(totalDuration / 1000).toFixed(1)}s total · ${readyCount} voices ready${
          busyTtsCount ? ` · ${busyTtsCount} generating` : ""
        }${dirty ? " · unsaved changes" : ""}`}
        crumbs={[
          { label: "Dashboard", to: "/dashboard" },
          { label: "Projects", to: "/projects" },
          { label: projectQuery.data?.title || "Editor" },
        ]}
        actions={
          <>
            <Button
              color="error"
              variant="outlined"
              startIcon={<StopIcon />}
              disabled={stopJobsMutation.isPending || busyTtsCount === 0}
              onClick={() => stopJobsMutation.mutate()}
            >
              {stopJobsMutation.isPending ? "Stopping…" : "Stop processes"}
            </Button>
            <Button
              variant="outlined"
              startIcon={<EditOutlinedIcon />}
              onClick={() => {
                setProjectFormError("");
                setEditProjectOpen(true);
              }}
            >
              Edit project
            </Button>
            <Button
              color="error"
              variant="outlined"
              startIcon={<DeleteOutlineIcon />}
              disabled={deleteProjectMutation.isPending}
              onClick={() => setDeleteProjectOpen(true)}
            >
              Delete
            </Button>
            <Button
              variant="contained"
              color="secondary"
              startIcon={<MovieCreationIcon />}
              component={RouterLink}
              to={`/projects/${projectId}/export`}
              disabled={slides.length === 0}
              onClick={async (e) => {
                try {
                  await saveDraftIfNeeded(draftRef.current);
                } catch (err) {
                  e.preventDefault();
                  setError(errMessage(err));
                }
              }}
            >
              Export video
            </Button>
          </>
        }
      />

      {error && (
        <Alert severity="error" onClose={() => setError("")}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert severity="success" onClose={() => setSuccess("")}>
          {success}
        </Alert>
      )}

      <StoryPanel projectId={projectId} defaultTopic={projectQuery.data?.title || ""} />

      <Card>
        <CardContent>
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <Chip
                size="small"
                color="primary"
                label={`${projectAspect.label} · ${projectAspect.width}×${projectAspect.height}`}
              />
              <Typography variant="body2" color="text.secondary">
                Any size is fine — images are scaled to fit {projectAspect.id} (
                {projectAspect.width}×{projectAspect.height}) with padding (no crop).
              </Typography>
            </Stack>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
              <Button
                variant="contained"
                startIcon={<NoteAddIcon />}
                disabled={createSlideMutation.isPending}
                onClick={() => createSlideMutation.mutate()}
              >
                {createSlideMutation.isPending ? "Creating…" : "Create slide"}
              </Button>
              <Button
                variant="outlined"
                component="label"
                startIcon={<CloudUploadIcon />}
                disabled={uploadAsSlidesMutation.isPending}
              >
                Upload as new slides
                <input
                  hidden
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  multiple
                  onChange={(e) => {
                    const picked = e.target.files ? Array.from(e.target.files) : [];
                    e.target.value = "";
                    if (picked.length) uploadAsSlidesMutation.mutate(picked);
                  }}
                />
              </Button>
              <Button
                variant="outlined"
                startIcon={<RecordVoiceOverIcon />}
                onClick={() => ttsBatch.mutate()}
                disabled={ttsBatch.isPending || slides.length === 0 || busyTtsCount > 0}
              >
                Generate all voices
              </Button>
              <Button
                color="error"
                variant="outlined"
                startIcon={<StopIcon />}
                disabled={stopJobsMutation.isPending || busyTtsCount === 0}
                onClick={() => stopJobsMutation.mutate()}
              >
                {stopJobsMutation.isPending ? "Stopping…" : "Stop generating"}
              </Button>
              {(uploadAsSlidesMutation.isPending || createSlideMutation.isPending) && (
                <CircularProgress size={22} />
              )}
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="stretch">
        <Card sx={{ width: { md: 320 }, flexShrink: 0 }}>
          <CardContent>
            <Typography variant="subtitle1" fontWeight={700} gutterBottom>
              Slides
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
              Drag ⋮⋮ to reorder · use ↑↓ or delete on each slide
            </Typography>
            <SlideList
              slides={slides}
              selectedId={selected?.id ?? null}
              dirtySelected={dirty}
              draftPreview={draft?.slideId === selected?.id ? draft?.text ?? null : null}
              disabled={reorderMutation.isPending || deleteMutation.isPending}
              onSelect={(id) => selectSlide(id)}
              onReorder={(ids) => reorderMutation.mutate(ids)}
              onDelete={(id) => {
                const s = slides.find((x) => x.id === id) || null;
                setDeleteTarget(s);
              }}
              onMove={moveSlide}
            />
          </CardContent>
        </Card>

        <Card sx={{ flex: 1 }}>
          <CardContent>
            {!selected && <Typography color="text.secondary">Select a slide to edit narration.</Typography>}
            {editorReady && selected && draft && (
              // key forces a clean editor remount when the slide changes
              <Stack spacing={2} key={selected.id}>
                {(selected.images?.length ?? 0) > 0 ? (
                  <Box
                    sx={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
                      gap: 1,
                    }}
                  >
                    {(selected.images || []).map((img) => (
                      <Box
                        key={`${img.image_key}-${img.index}`}
                        sx={{
                          position: "relative",
                          borderRadius: 2,
                          overflow: "hidden",
                          bgcolor: "#0f172a",
                          border: "1px solid",
                          borderColor: "divider",
                          "&:hover .img-actions": { opacity: 1 },
                        }}
                      >
                        <Box
                          component="img"
                          src={mediaUrl(img.image_url)}
                          alt={`Image ${img.index + 1}`}
                          onClick={() => setViewImageIndex(img.index)}
                          sx={{
                            width: "100%",
                            height: 120,
                            objectFit: "contain",
                            display: "block",
                            cursor: "zoom-in",
                          }}
                        />
                        <Stack
                          direction="row"
                          justifyContent="space-between"
                          alignItems="center"
                          className="img-actions"
                          sx={{ px: 0.5, py: 0.25, bgcolor: "rgba(0,0,0,0.6)" }}
                        >
                          <Typography variant="caption" color="#fff" sx={{ pl: 0.5 }}>
                            {img.index + 1}/{(selected.images || []).length}
                            {img.duration_ms != null
                              ? ` · ${(img.duration_ms / 1000).toFixed(1)}s`
                              : ""}
                          </Typography>
                          <Stack direction="row" spacing={0}>
                            <Tooltip title="View resized image">
                              <IconButton
                                size="small"
                                sx={{ color: "#fff" }}
                                onClick={() => setViewImageIndex(img.index)}
                                aria-label="View image"
                              >
                                <VisibilityIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Remove image">
                              <IconButton
                                size="small"
                                sx={{ color: "#fff" }}
                                disabled={removeImageMutation.isPending}
                                onClick={() => removeImageMutation.mutate(img.index)}
                                aria-label="Remove image"
                              >
                                <DeleteOutlineIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          </Stack>
                        </Stack>
                        {(selected.images?.length ?? 0) > 1 && (
                          <Box sx={{ px: 0.75, py: 0.75, bgcolor: "background.paper" }}>
                            <TextField
                              size="small"
                              type="number"
                              label="Seconds"
                              fullWidth
                              defaultValue={
                                img.duration_ms != null
                                  ? Math.round((img.duration_ms / 1000) * 10) / 10
                                  : ""
                              }
                              key={`${selected.id}-${img.index}-${img.duration_ms}`}
                              inputProps={{ min: 0.1, max: 120, step: 0.1 }}
                              onBlur={(e) => {
                                const sec = parseFloat(e.target.value);
                                if (!Number.isFinite(sec) || sec < 0.1) return;
                                const ms = Math.round(sec * 1000);
                                if (ms === img.duration_ms) return;
                                updateImageDurationMutation.mutate({
                                  index: img.index,
                                  durationMs: ms,
                                });
                              }}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  (e.target as HTMLInputElement).blur();
                                }
                              }}
                            />
                          </Box>
                        )}
                      </Box>
                    ))}
                  </Box>
                ) : (
                  <Box
                    sx={{
                      width: "100%",
                      minHeight: 160,
                      borderRadius: 2,
                      border: "2px dashed",
                      borderColor: "divider",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      bgcolor: "action.hover",
                      px: 2,
                    }}
                  >
                    <Typography color="text.secondary" align="center">
                      No images yet — add images (auto-resized to {projectAspect.id}).
                    </Typography>
                  </Box>
                )}

                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                  <Chip label={`Slide ${selected.order_index + 1}`} color="primary" size="small" />
                  <Chip
                    label={`${selected.image_count ?? selected.images?.length ?? 0} image${
                      (selected.image_count ?? selected.images?.length ?? 0) === 1 ? "" : "s"
                    }`}
                    size="small"
                  />
                  <Chip label={`${(selected.effective_duration_ms / 1000).toFixed(1)}s`} size="small" />
                  <Chip label={selected.narration?.tts_status || "missing"} size="small" />
                  {dirty && <Chip label="Unsaved" color="warning" size="small" />}
                  <Button
                    size="small"
                    variant="outlined"
                    component="label"
                    startIcon={<AddPhotoAlternateIcon />}
                    disabled={addImagesMutation.isPending}
                  >
                    {addImagesMutation.isPending ? "Adding…" : "Add images to slide"}
                    <input
                      hidden
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      multiple
                      onChange={(e) => {
                        const picked = e.target.files ? Array.from(e.target.files) : [];
                        e.target.value = "";
                        if (picked.length) addImagesMutation.mutate(picked);
                      }}
                    />
                  </Button>
                  {selected.narration?.tts_error && (
                    <Typography color="error" variant="caption">
                      {selected.narration.tts_error}
                    </Typography>
                  )}
                </Stack>
                {(selected.image_count ?? 0) > 1 && (
                  <Stack spacing={0.5}>
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                      <Typography variant="caption" color="text.secondary">
                        Set how long each image shows. Times are scaled to match narration length on
                        export.
                      </Typography>
                      <Button
                        size="small"
                        variant="text"
                        disabled={distributeDurationsMutation.isPending}
                        onClick={() => distributeDurationsMutation.mutate()}
                      >
                        Split evenly
                      </Button>
                    </Stack>
                    <Typography variant="caption" color="text.secondary">
                      Image times sum:{" "}
                      {(
                        (selected.images || []).reduce((a, im) => a + (im.duration_ms || 0), 0) / 1000
                      ).toFixed(1)}
                      s · narration {(selected.effective_duration_ms / 1000).toFixed(1)}s
                    </Typography>
                  </Stack>
                )}
                <TextField
                  label={`Narration script (slide ${selected.order_index + 1})`}
                  value={draft.text}
                  onChange={(e) => setDraft((d) => (d ? { ...d, text: e.target.value } : d))}
                  fullWidth
                  multiline
                  minRows={4}
                  placeholder="Write the spoken script for this slide…"
                  inputProps={{ "data-slide-id": selected.id }}
                />
                <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                  <FormControl fullWidth>
                    <InputLabel>TTS engine</InputLabel>
                    <Select
                      label="TTS engine"
                      value={engineFilter}
                      onChange={(e) => {
                        const eng = e.target.value;
                        setEngineFilter(eng);
                        const pool = allVoices.filter((v) => {
                          if (v.language !== languageFilter) return false;
                          if (eng === "deepgram")
                            return (v.providers || []).includes("deepgram") || v.provider === "deepgram";
                          if (eng === "edge") return v.provider === "edge";
                          return true;
                        });
                        const first =
                          pool.find((v) => v.gender === "female") || pool[0];
                        if (first) setDraft((d) => (d ? { ...d, voice: first.id } : d));
                      }}
                    >
                      <MenuItem value="all">All engines</MenuItem>
                      <MenuItem value="deepgram">
                        Deepgram Aura 2{deepgramAvailable ? "" : " (needs API key)"}
                      </MenuItem>
                      <MenuItem value="edge">Edge free</MenuItem>
                    </Select>
                  </FormControl>
                  <FormControl fullWidth>
                    <InputLabel>Language</InputLabel>
                    <Select
                      label="Language"
                      value={languageFilter}
                      onChange={(e) => {
                        const lang = e.target.value;
                        setLanguageFilter(lang);
                        const pool = allVoices.filter((v) => {
                          if (v.language !== lang) return false;
                          if (engineFilter === "deepgram")
                            return (v.providers || []).includes("deepgram") || v.provider === "deepgram";
                          if (engineFilter === "edge") return v.provider === "edge";
                          return true;
                        });
                        const first =
                          pool.find((v) => v.gender === "female") || pool[0];
                        if (first) {
                          setDraft((d) => (d ? { ...d, voice: first.id } : d));
                        }
                      }}
                    >
                      {languages.map((lang) => (
                        <MenuItem key={lang.code} value={lang.code}>
                          {lang.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <FormControl fullWidth>
                    <InputLabel>Voice</InputLabel>
                    <Select
                      label="Voice"
                      value={
                        voicesForLanguage.some((v) => v.id === draft.voice)
                          ? draft.voice
                          : voicesForLanguage[0]?.id || draft.voice
                      }
                      onChange={(e) => setDraft((d) => (d ? { ...d, voice: e.target.value } : d))}
                    >
                      {voicesForLanguage.map((v) => {
                        const isAura = (v.providers || []).includes("deepgram") || v.provider === "deepgram";
                        const tag = isAura ? "Aura 2" : "Edge";
                        const accent = v.accent ? ` · ${v.accent}` : "";
                        return (
                          <MenuItem key={v.id} value={v.id}>
                            {v.name} ({v.gender}) · {tag}
                            {accent}
                          </MenuItem>
                        );
                      })}
                    </Select>
                  </FormControl>
                  <FormControl fullWidth>
                    <InputLabel>Speed</InputLabel>
                    <Select
                      label="Speed"
                      value={String(draft.speed)}
                      onChange={(e) =>
                        setDraft((d) => (d ? { ...d, speed: Number(e.target.value) } : d))
                      }
                    >
                      {[0.8, 0.9, 1.0, 1.1, 1.2].map((s) => (
                        <MenuItem key={s} value={String(s)}>
                          {s}x
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Stack>
                {!deepgramAvailable && engineFilter === "deepgram" && (
                  <Alert severity="warning">
                    Deepgram Aura 2 needs <code>DEEPGRAM_API_KEY</code> in docker env. Without it,
                    Aura voices fall back to free Edge (or fail if no fallback).
                  </Alert>
                )}
                {deepgramAvailable &&
                  ((allVoices.find((v) => v.id === draft.voice)?.providers || []).includes("deepgram") ||
                    allVoices.find((v) => v.id === draft.voice)?.provider === "deepgram") && (
                    <Alert severity="info">
                      This voice will use <strong>Deepgram Aura 2</strong> (premium neural TTS).
                    </Alert>
                  )}
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={
                      applyLanguageMutation.isPending || !languageFilter || slides.length === 0
                    }
                    onClick={() => {
                      const voice =
                        voicesForLanguage.find((v) => v.id === draft.voice)?.id ||
                        voicesForLanguage[0]?.id;
                      if (!voice) return;
                      applyLanguageMutation.mutate({
                        language: languageFilter,
                        voice,
                        regenerate: false,
                      });
                    }}
                  >
                    Apply language to all slides
                  </Button>
                  <Button
                    size="small"
                    variant="text"
                    disabled={
                      applyLanguageMutation.isPending || !languageFilter || slides.length === 0
                    }
                    onClick={() => {
                      const voice =
                        voicesForLanguage.find((v) => v.id === draft.voice)?.id ||
                        voicesForLanguage[0]?.id;
                      if (!voice) return;
                      applyLanguageMutation.mutate({
                        language: languageFilter,
                        voice,
                        regenerate: true,
                      });
                    }}
                  >
                    Apply + regenerate all voices
                  </Button>
                  <Typography variant="caption" color="text.secondary">
                    Write narration in that language, then generate voice.
                  </Typography>
                </Stack>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                  <FormControl fullWidth>
                    <InputLabel>Transition</InputLabel>
                    <Select
                      label="Transition"
                      value={draft.transition}
                      onChange={(e) =>
                        setDraft((d) => (d ? { ...d, transition: e.target.value } : d))
                      }
                    >
                      <MenuItem value="fade">Fade</MenuItem>
                      <MenuItem value="none">None</MenuItem>
                    </Select>
                  </FormControl>
                  <FormControl fullWidth>
                    <InputLabel>Animation</InputLabel>
                    <Select
                      label="Animation"
                      value={draft.animation}
                      onChange={(e) =>
                        setDraft((d) => (d ? { ...d, animation: e.target.value } : d))
                      }
                    >
                      <MenuItem value="none">None (static)</MenuItem>
                      <MenuItem value="ken_burns">Ken Burns (slow zoom)</MenuItem>
                      <MenuItem value="wan_i2v">AI Motion (Wan2.1 1.3B)</MenuItem>
                      <MenuItem value="wan_t2v">Text to video (Wan2.1 T2V 1.3B)</MenuItem>
                    </Select>
                  </FormControl>
                </Stack>
                {(draft.animation === "wan_i2v" || draft.animation === "wan_t2v") && (
                  <>
                    <WanT2vBanner />
                    <TextField
                      label={draft.animation === "wan_t2v" ? "Video prompt (Wan2.1 T2V 1.3B)" : "Motion prompt (Wan2.1)"}
                      value={draft.motion_prompt}
                      onChange={(e) =>
                        setDraft((d) => (d ? { ...d, motion_prompt: e.target.value } : d))
                      }
                      fullWidth
                      multiline
                      minRows={2}
                      placeholder={
                        draft.animation === "wan_t2v"
                          ? "e.g. A lantern sways in a dark hallway as fog rolls across the floor"
                          : "e.g. Gentle camera push-in, leaves sway in the wind, soft cinematic lighting"
                      }
                      helperText={
                        draft.animation === "wan_t2v"
                          ? "Describes the whole clip. No still image is required. Runs locally with Diffusers or the official Wan script, not ComfyUI. Falls back to narration if empty."
                          : "Describes how the still should move (camera, wind, people walking…). Falls back to narration if empty. Real Wan2.1 needs FAL_KEY or REPLICATE_API_TOKEN in .env."
                      }
                    />
                  </>
                )}
                <Divider />
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Button
                    variant="outlined"
                    onClick={() => saveSlide.mutate()}
                    disabled={saveSlide.isPending || !dirty}
                  >
                    Save slide
                  </Button>
                  <Button
                    variant="contained"
                    startIcon={<RecordVoiceOverIcon />}
                    onClick={() => ttsOne.mutate(false)}
                    disabled={ttsOne.isPending || !draft.text.trim()}
                  >
                    Generate voice
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={<MovieCreationIcon />}
                    component={RouterLink}
                    to={`/projects/${projectId}/export?slide=${selected.id}`}
                    onClick={async (e) => {
                      try {
                        await saveDraftIfNeeded(draftRef.current);
                      } catch (err) {
                        e.preventDefault();
                        setError(errMessage(err));
                      }
                    }}
                  >
                    Generate this slide
                  </Button>
                  <Button
                    variant="text"
                    onClick={() => ttsOne.mutate(true)}
                    disabled={ttsOne.isPending || !draft.text.trim()}
                  >
                    Force regenerate
                  </Button>
                  <Button
                    color="error"
                    variant="outlined"
                    startIcon={<DeleteOutlineIcon />}
                    onClick={() => setDeleteTarget(selected)}
                    disabled={deleteMutation.isPending}
                  >
                    Delete slide
                  </Button>
                </Stack>
                {selected.narration?.audio_url && (
                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      Preview audio
                    </Typography>
                    {/* key remounts audio element when slide/audio changes */}
                    <audio
                      key={selected.narration.audio_url}
                      controls
                      src={mediaUrl(selected.narration.audio_url)}
                      style={{ width: "100%" }}
                    />
                  </Box>
                )}
              </Stack>
            )}
          </CardContent>
        </Card>
      </Stack>

      {/* Full-size view of auto-fitted / export image */}
      {(() => {
        const images = selected?.images || [];
        const idx = viewImageIndex;
        const current = idx != null ? images.find((i) => i.index === idx) || images[idx] : null;
        const ordered = images;
        const pos = current ? ordered.findIndex((i) => i.index === current.index) : -1;
        const canPrev = pos > 0;
        const canNext = pos >= 0 && pos < ordered.length - 1;
        const open = !!current && viewImageIndex != null;
        const src = mediaUrl(current?.image_url);

        return (
          <Dialog
            open={open}
            onClose={() => setViewImageIndex(null)}
            maxWidth="lg"
            fullWidth
            PaperProps={{
              sx: {
                bgcolor: "#0B1220",
                backgroundImage: "none",
                border: "1px solid",
                borderColor: "divider",
              },
            }}
          >
            <DialogTitle
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 1,
                color: "#F8FAFC",
                pr: 1,
              }}
            >
              <Box>
                <Typography variant="h6" fontWeight={700} component="span">
                  Resized image
                </Typography>
                <Typography variant="body2" color="rgba(248,250,252,0.65)" display="block">
                  Slide {(selected?.order_index ?? 0) + 1}
                  {current ? ` · ${current.index + 1} of ${ordered.length}` : ""}
                  {" · "}
                  canvas {projectAspect.id} ({projectAspect.width}×{projectAspect.height})
                </Typography>
              </Box>
              <Stack direction="row" spacing={0.5} alignItems="center">
                {src && (
                  <Tooltip title="Open in new tab">
                    <IconButton
                      size="small"
                      sx={{ color: "#F8FAFC" }}
                      onClick={() => window.open(src, "_blank", "noopener,noreferrer")}
                    >
                      <OpenInNewIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                )}
                <IconButton
                  size="small"
                  sx={{ color: "#F8FAFC" }}
                  onClick={() => setViewImageIndex(null)}
                  aria-label="Close"
                >
                  <CloseIcon />
                </IconButton>
              </Stack>
            </DialogTitle>
            <DialogContent sx={{ pt: 0 }}>
              <Box
                sx={{
                  position: "relative",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  minHeight: { xs: 280, sm: 420 },
                  bgcolor: "#020617",
                  borderRadius: 2,
                  border: "1px solid",
                  borderColor: "rgba(148,163,184,0.2)",
                  overflow: "hidden",
                }}
              >
                {/* Aspect-ratio frame guide */}
                <Box
                  sx={{
                    position: "absolute",
                    inset: 12,
                    border: "1px dashed",
                    borderColor: "rgba(167,139,250,0.35)",
                    borderRadius: 1,
                    pointerEvents: "none",
                    zIndex: 1,
                  }}
                />
                {src ? (
                  <Box
                    component="img"
                    src={src}
                    alt={`Fitted slide image ${current?.index != null ? current.index + 1 : ""}`}
                    sx={{
                      maxWidth: "100%",
                      maxHeight: { xs: "55vh", sm: "70vh" },
                      objectFit: "contain",
                      display: "block",
                      zIndex: 0,
                    }}
                  />
                ) : (
                  <Typography color="text.secondary">Image unavailable</Typography>
                )}
                {canPrev && (
                  <IconButton
                    onClick={() => setViewImageIndex(ordered[pos - 1].index)}
                    sx={{
                      position: "absolute",
                      left: 8,
                      top: "50%",
                      transform: "translateY(-50%)",
                      bgcolor: "rgba(15,23,42,0.75)",
                      color: "#fff",
                      zIndex: 2,
                      "&:hover": { bgcolor: "rgba(15,23,42,0.95)" },
                    }}
                    aria-label="Previous image"
                  >
                    <ChevronLeftIcon />
                  </IconButton>
                )}
                {canNext && (
                  <IconButton
                    onClick={() => setViewImageIndex(ordered[pos + 1].index)}
                    sx={{
                      position: "absolute",
                      right: 8,
                      top: "50%",
                      transform: "translateY(-50%)",
                      bgcolor: "rgba(15,23,42,0.75)",
                      color: "#fff",
                      zIndex: 2,
                      "&:hover": { bgcolor: "rgba(15,23,42,0.95)" },
                    }}
                    aria-label="Next image"
                  >
                    <ChevronRightIcon />
                  </IconButton>
                )}
              </Box>
              <Typography variant="caption" color="rgba(248,250,252,0.55)" sx={{ mt: 1.5, display: "block" }}>
                Full image is kept — scaled to fit {projectAspect.id} with black padding if the original
                aspect differs (no cropping).
              </Typography>
            </DialogContent>
            <DialogActions sx={{ px: 3, pb: 2 }}>
              <Button onClick={() => setViewImageIndex(null)} variant="contained">
                Close
              </Button>
            </DialogActions>
          </Dialog>
        );
      })()}

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete slide?"
        description="This permanently removes the image(s) and narration for this slide. This cannot be undone."
        highlight={
          deleteTarget ? `Slide ${(deleteTarget.order_index ?? 0) + 1}` : undefined
        }
        confirmLabel="Delete slide"
        loading={deleteMutation.isPending}
        tone="danger"
        onClose={() => {
          if (!deleteMutation.isPending) setDeleteTarget(null);
        }}
        onConfirm={() => {
          if (deleteTarget) deleteMutation.mutate(deleteTarget.id);
        }}
      />

      <ConfirmDialog
        open={deleteProjectOpen}
        title="Delete project?"
        description="This permanently removes the project, all slides, narration audio, and exported videos. This cannot be undone."
        highlight={projectQuery.data?.title}
        confirmLabel="Delete project"
        loading={deleteProjectMutation.isPending}
        tone="danger"
        onClose={() => {
          if (!deleteProjectMutation.isPending) setDeleteProjectOpen(false);
        }}
        onConfirm={() => deleteProjectMutation.mutate()}
      />

      <ProjectFormDialog
        open={editProjectOpen}
        mode="edit"
        project={projectQuery.data}
        loading={updateProjectMutation.isPending}
        error={projectFormError}
        onClose={() => {
          setEditProjectOpen(false);
          setProjectFormError("");
        }}
        onSubmit={(values) => {
          setProjectFormError("");
          updateProjectMutation.mutate(values);
        }}
      />
    </Stack>
  );
}
