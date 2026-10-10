import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  CardContent,
  Chip,
  Drawer,
  ListSubheader,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import AutoStoriesIcon from "@mui/icons-material/AutoStories";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import { api, errMessage, mediaUrl } from "../api/client";
import JobProgress from "./JobProgress";
import StoryReview, {
  type StoryCharacterView,
  type StoryLocationView,
  type StorySceneView,
  type StoryView,
} from "./StoryReview";

type FreeModel = { id: string; name: string; provider?: string };

type StageJob = {
  id: string;
  status: string;
  error: string | null;
  progress?: number;
  detail?: string | null;
  started_at?: string | null;
  created_at?: string | null;
};

type StoryPayload = {
  settings: {
    content_type?: string;
    topic?: string;
    duration_seconds?: number;
    language?: string;
    visual_style?: string;
    music_mode?: string;
    scene_count?: string;
    llm_model?: string;
  } | null;
  job: StageJob | null;
  music?: {
    job: StageJob | null;
    audio_url: string | null;
    filename: string | null;
  };
  images?: {
    job: StageJob | null;
  };
  story: StoryView | null;
  characters: StoryCharacterView[];
  locations: StoryLocationView[];
  scenes: StorySceneView[];
};

const DURATIONS = [30, 60, 140, 180, 300];

function StageProgress({
  job,
  pending = false,
  title,
  detail,
  unknownTimeNote,
  pinTitle = false,
}: {
  job: StageJob | null | undefined;
  pending?: boolean;
  title: string;
  detail: string;
  unknownTimeNote: string;
  pinTitle?: boolean;
}) {
  const live = !!job && (job.status === "queued" || job.status === "running");
  if (!live && !pending) return null;
  const waiting = !live || job?.status === "queued";
  const liveDetail = live ? job?.detail : null;
  return (
    <JobProgress
      active
      mode={waiting ? "waiting" : "working"}
      progress={live ? job?.progress || 0 : 0}
      title={pinTitle ? title : liveDetail || title}
      detail={pinTitle ? liveDetail || detail : detail}
      startedAt={live ? job?.started_at : null}
      createdAt={live ? job?.created_at : null}
      unknownTimeNote={unknownTimeNote}
    />
  );
}

function stageJobFrom(data: unknown): StageJob | null {
  if (!data || typeof data !== "object") return null;
  const row = data as Partial<StageJob>;
  if (!row.id || !row.status) return null;
  return row as StageJob;
}

function readStoryFile(file: File): Promise<Record<string, unknown>> {
  return file.text().then((text) => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new Error("That file is not valid JSON");
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("Story JSON must be an object");
    }
    const plan = parsed as Record<string, unknown>;
    if ("properties" in plan && !("scenes" in plan)) {
      throw new Error("Choose a story file, not the JSON schema");
    }
    if (!Array.isArray(plan.scenes)) {
      throw new Error("Story JSON needs a scenes list");
    }
    return plan;
  });
}

export default function StoryPanel({ projectId, defaultTopic }: { projectId: string; defaultTopic: string }) {
  const qc = useQueryClient();
  const [contentType, setContentType] = useState("horror");
  const [topic, setTopic] = useState(defaultTopic);
  const [duration, setDuration] = useState("140");
  const [language, setLanguage] = useState("en");
  const [visualStyle, setVisualStyle] = useState("Dark Horror");
  const [musicMode, setMusicMode] = useState("background");
  const [sceneCount, setSceneCount] = useState("auto");
  const [model, setModel] = useState("");
  const [storyJson, setStoryJson] = useState("");
  const [storyFileName, setStoryFileName] = useState("");
  const [schemaText, setSchemaText] = useState("");
  const [schemaOpen, setSchemaOpen] = useState(false);
  const [formError, setFormError] = useState("");
  const [reviewOpen, setReviewOpen] = useState(false);
  const modelTouched = useRef(false);
  const formTouched = useRef(false);

  const modelsQuery = useQuery({
    queryKey: ["story-models"],
    queryFn: async () =>
      (await api.get("/models")).data as {
        default_model: string;
        key_configured: boolean;
        gemini_key_configured?: boolean;
        openai_key_configured?: boolean;
        local_available?: boolean;
        local_base_url?: string;
        models: FreeModel[];
      },
    refetchOnMount: "always",
  });

  const storyQuery = useQuery({
    queryKey: ["story", projectId],
    queryFn: async () => (await api.get(`/projects/${projectId}/story`)).data as StoryPayload,
  });

  useEffect(() => {
    if (formTouched.current) return;
    const saved = storyQuery.data?.settings;
    if (!saved) return;
    if (saved.content_type) setContentType(saved.content_type);
    if (saved.topic) setTopic(saved.topic);
    if (saved.duration_seconds) setDuration(String(saved.duration_seconds));
    if (saved.language) setLanguage(saved.language);
    if (saved.visual_style) setVisualStyle(saved.visual_style);
    if (saved.music_mode) setMusicMode(saved.music_mode);
    if (saved.scene_count) setSceneCount(saved.scene_count);
  }, [storyQuery.data?.settings]);

  useEffect(() => {
    if (modelTouched.current) return;
    const localDefault = (modelsQuery.data?.models ?? []).find((item) => item.provider === "local");
    if (localDefault) {
      setModel(localDefault.id);
      return;
    }
    const savedModel = storyQuery.data?.settings?.llm_model;
    if (savedModel) setModel(savedModel);
    else if (modelsQuery.data?.default_model) setModel(modelsQuery.data.default_model);
  }, [modelsQuery.data?.models, modelsQuery.data?.default_model, storyQuery.data?.settings?.llm_model]);

  const showSchema = async () => {
    if (schemaOpen) {
      setSchemaOpen(false);
      return;
    }
    if (!schemaText) {
      const response = await api.get("/projects/story-schema");
      setSchemaText(JSON.stringify(response.data.schema, null, 2));
    }
    setSchemaOpen(true);
  };

  const choose = (setter: (value: string) => void) => (event: { target: { value: string } }) => {
    formTouched.current = true;
    setter(event.target.value);
  };

  const loadStoryFile = async (file: File) => {
    formTouched.current = true;
    const plan = await readStoryFile(file);
    setStoryJson(JSON.stringify(plan, null, 2));
    setStoryFileName(file.name);
    setFormError("");
    if (typeof plan.title === "string" && plan.title.trim()) setTopic(plan.title.trim());
    const scenes = plan.scenes as Array<Record<string, unknown>>;
    const end = Number(scenes[scenes.length - 1]?.end_time);
    const match = DURATIONS.find((seconds) => Number.isFinite(end) && Math.abs(seconds - end) < 0.5);
    if (match) setDuration(String(match));
    const sample = `${plan.hook ?? ""} ${plan.story ?? ""}`;
    if (/[\u0900-\u097F]/.test(sample)) setLanguage("hi");
    if (typeof plan.kids_format === "string" && plan.kids_format.trim()) setContentType("kids");
    else setContentType("horror");
  };

  const clearStoryFile = () => {
    setStoryFileName("");
    setStoryJson("");
  };

  const generate = useMutation({
    mutationFn: async () => {
      let plan: Record<string, unknown> | undefined;
      if (storyJson.trim()) {
        let parsed: unknown;
        try {
          parsed = JSON.parse(storyJson);
        } catch {
          throw new Error("Story JSON is not valid JSON");
        }
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("Story JSON must be an object");
        }
        plan = parsed as Record<string, unknown>;
      }
      await api.post(`/projects/${projectId}/story`, {
        content_type: contentType,
        topic: topic.trim() || String(plan?.title || ""),
        duration_seconds: Number(duration),
        language,
        visual_style: visualStyle,
        music_mode: musicMode,
        scene_count: sceneCount,
        llm_model: model || undefined,
        plan,
      });
    },
    onSuccess: async () => {
      setFormError("");
      setStoryJson("");
      setStoryFileName("");
      await qc.invalidateQueries({ queryKey: ["story", projectId] });
      await qc.invalidateQueries({ queryKey: ["slides", projectId] });
    },
    onError: (error) => setFormError(errMessage(error)),
  });

  const generateMusic = useMutation({
    mutationFn: async () => (await api.post(`/projects/${projectId}/music/generate`, { music_mode: musicMode })).data,
    onSuccess: async (data) => {
      setFormError("");
      const next = stageJobFrom(data);
      if (next) {
        qc.setQueryData<StoryPayload>(["story", projectId], (current) =>
          current
            ? {
                ...current,
                music: {
                  job: next,
                  audio_url: current.music?.audio_url ?? null,
                  filename: current.music?.filename ?? null,
                },
              }
            : current
        );
      }
      await qc.invalidateQueries({ queryKey: ["story", projectId] });
    },
    onError: (error) => setFormError(errMessage(error)),
  });

  const generateImages = useMutation({
    mutationFn: async (force: boolean) =>
      (await api.post(`/projects/${projectId}/images/generate`, { force })).data,
    onSuccess: async (data) => {
      setFormError("");
      const next = stageJobFrom(data);
      if (next) {
        qc.setQueryData<StoryPayload>(["story", projectId], (current) =>
          current ? { ...current, images: { job: next } } : current
        );
      }
      await qc.invalidateQueries({ queryKey: ["story", projectId] });
    },
    onError: (error) => setFormError(errMessage(error)),
  });

  const slidesQuery = useQuery({
    queryKey: ["slides", projectId],
    queryFn: async () =>
      (await api.get(`/projects/${projectId}/slides`)).data as {
        image_count?: number;
        narration?: { text?: string } | null;
      }[],
  });

  const buildSlides = useMutation({
    mutationFn: async () => (await api.post(`/projects/${projectId}/story/slides`)).data as { slides: number },
    onSuccess: async () => {
      setFormError("");
      await qc.invalidateQueries({ queryKey: ["slides", projectId] });
    },
    onError: (error) => setFormError(errMessage(error)),
  });

  const story = storyQuery.data?.story;
  const scenes = storyQuery.data?.scenes ?? [];
  const slides = slidesQuery.data ?? [];
  const slidesBlank = slides.every(
    (slide) => !(slide.narration?.text || "").trim() && (slide.image_count || 0) === 0
  );
  const slidesMatch = scenes.length > 0 && slides.length === scenes.length;
  const builtSlides = useRef(false);
  const job = storyQuery.data?.job;
  const planning = job?.status === "queued" || job?.status === "running" || generate.isPending;
  const musicJob = storyQuery.data?.music?.job;
  const musicBusy = musicJob?.status === "queued" || musicJob?.status === "running" || generateMusic.isPending;
  const imageJob = storyQuery.data?.images?.job;
  const imageBusy = imageJob?.status === "queued" || imageJob?.status === "running" || generateImages.isPending;
  const redrawExisting = slides.length > 0 && slides.every((slide) => (slide.image_count || 0) > 0);
  const models = modelsQuery.data?.models ?? [];
  const openaiModels = models.filter((item) => item.provider === "openai");
  const geminiModels = models.filter((item) => item.provider === "gemini");
  const localModels = models.filter((item) => item.provider === "local");
  const openRouterModels = models.filter(
    (item) => item.provider !== "gemini" && item.provider !== "openai" && item.provider !== "local"
  );
  const selectedModel = models.find((item) => item.id === model);
  const missingGeminiKey = selectedModel?.provider === "gemini" && !modelsQuery.data?.gemini_key_configured;
  const missingOpenAIKey = selectedModel?.provider === "openai" && !modelsQuery.data?.openai_key_configured;
  const missingLocal = selectedModel?.provider === "local" && modelsQuery.data && !modelsQuery.data.local_available;
  const missingOpenRouterKey =
    !!selectedModel &&
    selectedModel.provider !== "gemini" &&
    selectedModel.provider !== "openai" &&
    selectedModel.provider !== "local" &&
    modelsQuery.data &&
    !modelsQuery.data.key_configured;
  const audioSrc = mediaUrl(storyQuery.data?.music?.audio_url);
  const videoCount = scenes.filter((scene) => scene.generation_mode === "video").length;

  useEffect(() => {
    if (planning || !story || scenes.length === 0 || !slidesQuery.isSuccess || slidesMatch) return;
    if (slides.length > 0 && !slidesBlank) return;
    if (buildSlides.isPending || builtSlides.current) return;
    builtSlides.current = true;
    buildSlides.mutate();
  }, [planning, story, scenes.length, slidesQuery.isSuccess, slidesMatch, slides.length, slidesBlank, buildSlides]);

  return (
    <Stack spacing={2}>
      <Card>
        <CardContent>
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between" flexWrap="wrap" useFlexGap>
              <Stack direction="row" spacing={1} alignItems="center">
                <AutoStoriesIcon color="primary" />
                <Typography variant="h6" fontWeight={800}>
                  AI story
                </Typography>
              </Stack>
              <Button variant="contained" component="label" startIcon={<CloudUploadIcon />} disabled={planning}>
                Add story JSON
                <input
                  hidden
                  type="file"
                  accept=".json,application/json"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (!file) return;
                    void loadStoryFile(file).catch((error) => setFormError(errMessage(error)));
                  }}
                />
              </Button>
            </Stack>
            {storyFileName && (
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <Chip size="small" color="primary" label={storyFileName} onDelete={clearStoryFile} />
                <Typography variant="caption" color="text.secondary">
                  Loaded. Check type, length, and language, then press Use story JSON.
                </Typography>
              </Stack>
            )}
            <Typography variant="body2" color="text.secondary">
              The model writes an original story from the type, length, language, style, and music selected here, then
              splits it into scenes. Wan clips stay inside about a quarter of the runtime.
            </Typography>
            {missingOpenRouterKey && (
              <Alert severity="warning">Add OPENROUTER_API_KEY to the environment before generating a story.</Alert>
            )}
            {missingGeminiKey && (
              <Alert severity="warning">Add GEMINI_API_KEY to the environment before generating a story with Gemini.</Alert>
            )}
            {missingOpenAIKey && (
              <Alert severity="warning">Add OPENAI_API_KEY to the environment before generating a story with OpenAI.</Alert>
            )}
            {missingLocal && (
              <Alert severity="warning">
                The local model server is not running at {modelsQuery.data?.local_base_url || "http://127.0.0.1:11434/v1"}.
                Start Ollama or LM Studio, then generate the story again.
              </Alert>
            )}
            {formError && (
              <Alert severity="error" onClose={() => setFormError("")}>
                {formError}
              </Alert>
            )}
            {job?.status === "failed" && job.error && <Alert severity="error">{job.error}</Alert>}
            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
              <TextField select label="Type" value={contentType} onChange={choose(setContentType)} fullWidth>
                <MenuItem value="horror">Horror</MenuItem>
                <MenuItem value="kids">Kids</MenuItem>
              </TextField>
              <TextField select label="Length" value={duration} onChange={choose(setDuration)} fullWidth>
                {DURATIONS.map((seconds) => (
                  <MenuItem key={seconds} value={String(seconds)}>
                    {seconds}s
                  </MenuItem>
                ))}
              </TextField>
              <TextField select label="Language" value={language} onChange={choose(setLanguage)} fullWidth>
                <MenuItem value="en">English</MenuItem>
                <MenuItem value="hi">Hindi</MenuItem>
                <MenuItem value="hinglish">Hinglish</MenuItem>
              </TextField>
            </Stack>
            <TextField
              label="Topic"
              value={topic}
              onChange={choose(setTopic)}
              fullWidth
              multiline
              minRows={2}
              maxRows={4}
            />
            <Stack spacing={1}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Button size="small" variant="text" onClick={() => void showSchema().catch((error) => setFormError(errMessage(error)))}>
                  {schemaOpen ? "Hide JSON schema" : "JSON schema"}
                </Button>
                <Typography variant="caption" color="text.secondary">
                  Or paste a story object below. Open the schema to see the fields.
                </Typography>
              </Stack>
              {schemaOpen && (
                <TextField
                  label="JSON schema"
                  value={schemaText}
                  multiline
                  minRows={8}
                  fullWidth
                  InputProps={{ readOnly: true, sx: { fontFamily: "monospace", fontSize: 12 } }}
                />
              )}
              <TextField
                label="Story JSON"
                value={storyJson}
                onChange={(e) => setStoryJson(e.target.value)}
                fullWidth
                multiline
                minRows={4}
                placeholder='{"title": "...", "hook": "...", "story": "...", "characters": [], "locations": [], "scenes": []}'
                helperText="Optional. Choose Add story JSON, or paste a story object here. Type, length, language, style, and music above still apply."
                InputProps={{ sx: { fontFamily: "monospace", fontSize: 13 } }}
              />
            </Stack>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
              <TextField
                select
                label="Style"
                value={visualStyle}
                onChange={choose(setVisualStyle)}
                fullWidth
              >
                {["Dark Horror", "Cinematic", "3D Cartoon", "2D Cartoon", "Kids Animation", "Anime"].map((style) => (
                  <MenuItem key={style} value={style}>
                    {style}
                  </MenuItem>
                ))}
              </TextField>
              <TextField select label="Music" value={musicMode} onChange={choose(setMusicMode)} fullWidth>
                <MenuItem value="background">Background</MenuItem>
                <MenuItem value="full_song">Full song</MenuItem>
                <MenuItem value="none">None</MenuItem>
              </TextField>
              <TextField
                select
                label="Model"
                value={model}
                onChange={(e) => {
                  modelTouched.current = true;
                  setModel(e.target.value);
                }}
                fullWidth
                SelectProps={{
                  MenuProps: {
                    variant: "menu",
                    PaperProps: { sx: { maxHeight: 360 } },
                  },
                }}
              >
                {openaiModels.length > 0 && <ListSubheader>OpenAI</ListSubheader>}
                {openaiModels.map((item) => (
                  <MenuItem key={item.id} value={item.id}>
                    {item.name}
                  </MenuItem>
                ))}
                {geminiModels.length > 0 && <ListSubheader>Gemini</ListSubheader>}
                {geminiModels.map((item) => (
                  <MenuItem key={item.id} value={item.id}>
                    {item.name}
                  </MenuItem>
                ))}
                {localModels.length > 0 && <ListSubheader>Local</ListSubheader>}
                {localModels.map((item) => (
                  <MenuItem key={item.id} value={item.id}>
                    {item.name}
                  </MenuItem>
                ))}
                {openRouterModels.length > 0 && <ListSubheader>OpenRouter</ListSubheader>}
                {openRouterModels.map((item) => (
                  <MenuItem key={item.id} value={item.id}>
                    {item.name}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            {localModels.length === 0 && (
              <Typography variant="caption" color="text.secondary">
                Local models appear in the Model list when Ollama or LM Studio is running at{" "}
                {modelsQuery.data?.local_base_url || "http://127.0.0.1:11434/v1"}.
              </Typography>
            )}
            <Button
              variant="contained"
              disabled={planning || (!topic.trim() && !storyJson.trim())}
              onClick={() => generate.mutate()}
              sx={{ alignSelf: "flex-start" }}
            >
              {planning
                ? "Writing the story…"
                : storyJson.trim()
                  ? "Use story JSON"
                  : story
                    ? "Regenerate story"
                    : "Generate story"}
            </Button>
            <Typography variant="caption" color="text.secondary">
              Choose a Local model to write the story on this PC. Story planning, music, and scene images run on the
              Celery worker. That worker must listen to story-generation, music-generation, and image-generation. Wan
              stays on the render worker.
            </Typography>
            <StageProgress
              job={job}
              title="Writing the story"
              detail="The model writes the whole plan in one pass."
              unknownTimeNote="The percent stays at 0 until the model returns the story. Time left shows while the scenes are saved."
            />
            {story && musicMode !== "none" && (
              <Stack spacing={1} alignItems="flex-start">
                <Button variant="outlined" disabled={planning || musicBusy} onClick={() => generateMusic.mutate()}>
                  {musicBusy ? "Generating music…" : audioSrc ? "Regenerate music" : "Generate music"}
                </Button>
                <StageProgress
                  job={musicJob}
                  pending={generateMusic.isPending}
                  pinTitle
                  title="Generating music"
                  detail="ACE-Step writes one track for the whole video."
                  unknownTimeNote="Time left appears if ACE-Step reports a percent. Until then this shows how long it has been writing."
                />
                <Typography variant="caption" color="text.secondary">
                  ACE-Step writes one full track for the whole video, following every scene. Horror background stays
                  instrumental. Kids stories and Full song sing the original lyrics from start to finish.
                </Typography>
                {musicJob?.status === "failed" && musicJob.error && <Alert severity="error">{musicJob.error}</Alert>}
                {audioSrc && <audio controls src={audioSrc} />}
              </Stack>
            )}
            {story && musicMode === "none" && (
              <Typography variant="body2" color="text.secondary">
                Music is off, so ACE-Step is not called.
              </Typography>
            )}
            {story && (
              <Stack spacing={1} alignItems="flex-start">
                <Button
                  variant="outlined"
                  disabled={planning || imageBusy}
                  onClick={() => generateImages.mutate(redrawExisting)}
                >
                  {imageBusy
                    ? "Generating scene images…"
                    : redrawExisting
                      ? "Regenerate scene images"
                      : "Generate scene images"}
                </Button>
                <StageProgress
                  job={imageJob}
                  pending={generateImages.isPending}
                  pinTitle
                  title="Generating scene images"
                  detail="ComfyUI draws one scene at a time."
                  unknownTimeNote="Time left appears after the first scene, or the first ComfyUI step, moves the percent."
                />
                <Typography variant="caption" color="text.secondary">
                  ComfyUI on port 8188 draws each scene with Qwen-Image-2.1. Slides that already have a picture are
                  kept until you regenerate. The image-generation queue must be on the non-render Celery worker.
                </Typography>
                {imageJob?.status === "failed" && imageJob.error && <Alert severity="error">{imageJob.error}</Alert>}
              </Stack>
            )}
            {story && (
              <Stack
                direction={{ xs: "column", sm: "row" }}
                spacing={1.5}
                alignItems={{ xs: "stretch", sm: "center" }}
                justifyContent="space-between"
              >
                <Stack spacing={0.75} sx={{ minWidth: 0 }}>
                  <Typography variant="subtitle1" fontWeight={800} sx={{ overflowWrap: "anywhere" }}>
                    {story.title}
                  </Typography>
                  {story.hook && (
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}
                    >
                      {story.hook}
                    </Typography>
                  )}
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                    <Chip size="small" color="primary" label={`${scenes.length} scenes`} />
                    <Chip size="small" label={`${videoCount} video · ${scenes.length - videoCount} image`} />
                  </Stack>
                </Stack>
                <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
                  {!slidesMatch && (
                    <Button
                      variant="contained"
                      disabled={planning || buildSlides.isPending}
                      onClick={() => buildSlides.mutate()}
                    >
                      {buildSlides.isPending ? "Creating slides…" : "Create slides"}
                    </Button>
                  )}
                  <Button variant="outlined" onClick={() => setReviewOpen(true)}>
                    Review story
                  </Button>
                </Stack>
              </Stack>
            )}
          </Stack>
        </CardContent>
      </Card>
      <Drawer
        anchor="right"
        open={reviewOpen && Boolean(story)}
        onClose={() => setReviewOpen(false)}
        PaperProps={{
          sx: { width: { xs: "100%", sm: 520, md: 680 }, maxWidth: "100%" },
        }}
      >
        {story && (
          <StoryReview
            story={story}
            scenes={scenes}
            characters={storyQuery.data?.characters ?? []}
            locations={storyQuery.data?.locations ?? []}
            onClose={() => setReviewOpen(false)}
          />
        )}
      </Drawer>
    </Stack>
  );
}
