import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  CardContent,
  Chip,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import AutoStoriesIcon from "@mui/icons-material/AutoStories";
import { api, errMessage } from "../api/client";

type FreeModel = { id: string; name: string };

type StoryScene = {
  id: string;
  index: number;
  beat: string;
  narration: string;
  duration: number;
  generation_mode: string;
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
  job: { id: string; status: string; error: string | null } | null;
  story: { title: string; hook: string; body: string; lyrics: string | null } | null;
  scenes: StoryScene[];
};

const DURATIONS = [30, 60, 140, 180, 300];

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
  const [formError, setFormError] = useState("");

  const modelsQuery = useQuery({
    queryKey: ["openrouter-models"],
    queryFn: async () =>
      (await api.get("/models")).data as {
        default_model: string;
        key_configured: boolean;
        models: FreeModel[];
      },
  });

  const storyQuery = useQuery({
    queryKey: ["story", projectId],
    queryFn: async () => (await api.get(`/projects/${projectId}/story`)).data as StoryPayload,
    refetchInterval: (query) => {
      const status = query.state.data?.job?.status;
      return status === "queued" || status === "running" ? 2000 : false;
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

  const generate = useMutation({
    mutationFn: async () => {
      await api.post(`/projects/${projectId}/story`, {
        content_type: contentType,
        topic: topic.trim(),
        duration_seconds: Number(duration),
        language,
        visual_style: visualStyle,
        music_mode: musicMode,
        scene_count: sceneCount,
        llm_model: model || undefined,
      });
    },
    onSuccess: async () => {
      setFormError("");
      await qc.invalidateQueries({ queryKey: ["story", projectId] });
    },
    onError: (error) => setFormError(errMessage(error)),
  });

  const story = storyQuery.data?.story;
  const scenes = storyQuery.data?.scenes ?? [];
  const job = storyQuery.data?.job;
  const planning = job?.status === "queued" || job?.status === "running" || generate.isPending;
  const models = modelsQuery.data?.models ?? [];

  return (
    <Card>
      <CardContent>
        <Stack spacing={2}>
          <Stack direction="row" spacing={1} alignItems="center">
            <AutoStoriesIcon color="primary" />
            <Typography variant="h6" fontWeight={800}>
              AI story
            </Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary">
            OpenRouter writes an original horror story or kids song, then splits it into scenes. Wan clips stay inside
            about a quarter of the runtime.
          </Typography>
          {modelsQuery.data && !modelsQuery.data.key_configured && (
            <Alert severity="warning">Add OPENROUTER_API_KEY to the environment before generating a story.</Alert>
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
            >
              {models.map((item) => (
                <MenuItem key={item.id} value={item.id}>
                  {item.name}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
          <Button
            variant="contained"
            disabled={planning || !topic.trim()}
            onClick={() => generate.mutate()}
            sx={{ alignSelf: "flex-start" }}
          >
            {planning ? "Writing the story…" : story ? "Regenerate story" : "Generate story"}
          </Button>
          {story && (
            <Stack spacing={1}>
              <Typography variant="subtitle1" fontWeight={800}>
                {story.title}
              </Typography>
              <Typography variant="body2">{story.hook}</Typography>
              <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                {story.body}
              </Typography>
              {story.lyrics && (
                <Typography
                  variant="body2"
                  sx={{ whiteSpace: "pre-wrap", bgcolor: "rgba(109,40,217,0.06)", borderRadius: 2, p: 1.5 }}
                >
                  {story.lyrics}
                </Typography>
              )}
            </Stack>
          )}
          {scenes.map((scene) => (
            <Stack key={scene.id} direction="row" spacing={1} alignItems="flex-start">
              <Chip size="small" label={scene.generation_mode === "video" ? "Video" : "Image"} />
              <Typography variant="body2">
                {scene.index + 1}. {scene.beat ? `${scene.beat} · ` : ""}
                {scene.narration}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}
