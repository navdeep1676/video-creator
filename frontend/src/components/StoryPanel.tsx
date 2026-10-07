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
import StoryReview, {
  type StoryCharacterView,
  type StoryLocationView,
  type StorySceneView,
  type StoryView,
} from "./StoryReview";

type FreeModel = { id: string; name: string; provider?: string };

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
  job: { id: string; status: string; error: string | null } | null;
  music?: {
    job: { id: string; status: string; error: string | null } | null;
    audio_url: string | null;
    filename: string | null;
  };
  images?: {
    job: { id: string; status: string; error: string | null } | null;
  };
  story: StoryView | null;
  characters: StoryCharacterView[];
  locations: StoryLocationView[];
  scenes: StorySceneView[];
};

const DURATIONS = [30, 60, 140, 180, 300];

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
    refetchInterval: (query) => {
      const storyStatus = query.state.data?.job?.status;
      const musicStatus = query.state.data?.music?.job?.status;
      const imageStatus = query.state.data?.images?.job?.status;
      const active = (status?: string) => status === "queued" || status === "running";
      return active(storyStatus) || active(musicStatus) || active(imageStatus) ? 2000 : false;
    },
  });

  useEffect(() => {
    const saved = storyQuery.data?.settings;
    if (!saved) return;
    if (saved.content_type) setContentType(saved.content_type);
    if (saved.topic) setTopic(saved.topic);
    if (saved.duration_seconds) setDuration(String(saved.duration_seconds));
    if (saved.language) setLanguage(saved.language);
    if (saved.visual_style) setVisualStyle(saved.visual_style);
    if (saved.music_mode) setMusicMode(saved.music_mode);
    if (saved.scene_count) setSceneCount(saved.scene_count);
    if (saved.llm_model) setModel(saved.llm_model);
  }, [storyQuery.data?.settings]);

  useEffect(() => {
    if (!model && modelsQuery.data?.default_model) setModel(modelsQuery.data.default_model);
  }, [model, modelsQuery.data?.default_model]);

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

  const loadStoryFile = async (file: File) => {
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
    onSuccess: async () => {
      setFormError("");
      await qc.invalidateQueries({ queryKey: ["story", projectId] });
    },
    onError: (error) => setFormError(errMessage(error)),
  });

  const generateImages = useMutation({
    mutationFn: async (force: boolean) =>
      (await api.post(`/projects/${projectId}/images/generate`, { force })).data,
    onSuccess: async () => {
      setFormError("");
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
  const jobStatus = job?.status ?? null;
  const previousJobStatus = useRef<string | null>(null);
  const imageJobStatus = imageJob?.status ?? null;
  const previousImageStatus = useRef<string | null>(null);

  useEffect(() => {
    if (previousJobStatus.current && previousJobStatus.current !== "succeeded" && jobStatus === "succeeded") {
      void qc.invalidateQueries({ queryKey: ["slides", projectId] });
    }
    previousJobStatus.current = jobStatus;
  }, [jobStatus, projectId, qc]);

  useEffect(() => {
    if (
      previousImageStatus.current &&
      previousImageStatus.current !== "succeeded" &&
      imageJobStatus === "succeeded"
    ) {
      void qc.invalidateQueries({ queryKey: ["slides", projectId] });
    }
    previousImageStatus.current = imageJobStatus;
  }, [imageJobStatus, projectId, qc]);

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
              OpenRouter, Gemini, OpenAI, or a local model writes an original horror story or kids song, then splits it
              into scenes. Wan clips stay inside about a quarter of the runtime.
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
              <TextField select label="Type" value={contentType} onChange={(e) => setContentType(e.target.value)} fullWidth>
                <MenuItem value="horror">Horror</MenuItem>
                <MenuItem value="kids">Kids</MenuItem>
              </TextField>
              <TextField select label="Length" value={duration} onChange={(e) => setDuration(e.target.value)} fullWidth>
                {DURATIONS.map((seconds) => (
                  <MenuItem key={seconds} value={String(seconds)}>
                    {seconds}s
                  </MenuItem>
                ))}
              </TextField>
              <TextField select label="Language" value={language} onChange={(e) => setLanguage(e.target.value)} fullWidth>
                <MenuItem value="en">English</MenuItem>
                <MenuItem value="hi">Hindi</MenuItem>
                <MenuItem value="hinglish">Hinglish</MenuItem>
              </TextField>
            </Stack>
            <TextField label="Topic" value={topic} onChange={(e) => setTopic(e.target.value)} fullWidth multiline minRows={2} />
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
                helperText="Optional. Choose Add story JSON, or paste a story object here. Type, length, and style above still apply."
                InputProps={{ sx: { fontFamily: "monospace", fontSize: 13 } }}
              />
            </Stack>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
              <TextField
                select
                label="Style"
                value={visualStyle}
                onChange={(e) => setVisualStyle(e.target.value)}
                fullWidth
              >
                {["Dark Horror", "Cinematic", "3D Cartoon", "2D Cartoon", "Kids Animation", "Anime"].map((style) => (
                  <MenuItem key={style} value={style}>
                    {style}
                  </MenuItem>
                ))}
              </TextField>
              <TextField select label="Music" value={musicMode} onChange={(e) => setMusicMode(e.target.value)} fullWidth>
                <MenuItem value="background">Background</MenuItem>
                <MenuItem value="full_song">Full song</MenuItem>
                <MenuItem value="none">None</MenuItem>
              </TextField>
              <TextField
                select
                label="Model"
                value={model}
                onChange={(e) => setModel(e.target.value)}
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
            {story && musicMode !== "none" && (
              <Stack spacing={1} alignItems="flex-start">
                <Button variant="outlined" disabled={planning || musicBusy} onClick={() => generateMusic.mutate()}>
                  {musicBusy ? "Writing music…" : audioSrc ? "Regenerate music" : "Generate music"}
                </Button>
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
                  {imageBusy ? "Drawing scenes…" : redrawExisting ? "Regenerate scene images" : "Generate scene images"}
                </Button>
                <Typography variant="caption" color="text.secondary">
                  ComfyUI on port 8188 draws each scene with Qwen-Image-2.1. Slides that already have a picture are
                  kept until you regenerate. Start the Celery worker before you press this.
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
