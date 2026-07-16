import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  CircularProgress,
  FormControlLabel,
  LinearProgress,
  Slider,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import ContentCutIcon from "@mui/icons-material/ContentCut";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";
import MovieCreationIcon from "@mui/icons-material/MovieCreation";
import SelectAllIcon from "@mui/icons-material/SelectAll";
import DeselectIcon from "@mui/icons-material/Deselect";
import { api, errMessage, mediaUrl } from "../api/client";
import PageHeader from "../components/PageHeader";

type ClipFrame = {
  id: string;
  time_ms: number;
  time_label: string;
  image_url: string;
  selected: boolean;
  narration: string;
};

type ClipSession = {
  id: string;
  filename: string;
  duration_ms: number;
  duration_label: string;
  video_url: string;
  frame_count: number;
  selected_count: number;
  max_frames: number;
  frames: ClipFrame[];
};

export default function ClipperPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [intervalS, setIntervalS] = useState(3);
  const [maxFrames, setMaxFrames] = useState(30);
  const [title, setTitle] = useState("");
  const [generateTts, setGenerateTts] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [uploading, setUploading] = useState(false);

  const sessionQuery = useQuery({
    queryKey: ["clipper-session", sessionId],
    enabled: !!sessionId,
    queryFn: async () => (await api.get(`/clipper/${sessionId}`)).data as ClipSession,
  });

  const session = sessionQuery.data;
  const frames = session?.frames || [];
  const selectedCount = frames.filter((f) => f.selected).length;

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post("/clipper/upload", form);
      return data as { session: ClipSession; estimated_frames_at_3s: number };
    },
    onSuccess: (data) => {
      setSessionId(data.session.id);
      setTitle(data.session.filename.replace(/\.[^.]+$/, "") || "Clipped video lesson");
      qc.setQueryData(["clipper-session", data.session.id], data.session);
      setSuccess("Video uploaded — choose an interval and extract frames");
      setError("");
    },
    onError: (e) => setError(errMessage(e)),
    onSettled: () => setUploading(false),
  });

  const extractMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post(`/clipper/${sessionId}/extract`, {
        interval_s: intervalS,
        max_frames: maxFrames,
      });
      return data as ClipSession;
    },
    onSuccess: (data) => {
      qc.setQueryData(["clipper-session", data.id], data);
      setSuccess(`Extracted ${data.frame_count} frames — add narration, then create a project`);
      setError("");
    },
    onError: (e) => setError(errMessage(e)),
  });

  const saveFramesMutation = useMutation({
    mutationFn: async (updates: { frame_id: string; selected?: boolean; narration?: string }[]) => {
      const { data } = await api.patch(`/clipper/${sessionId}/frames`, { frames: updates });
      return data as ClipSession;
    },
    onSuccess: (data) => {
      qc.setQueryData(["clipper-session", data.id], data);
    },
    onError: (e) => setError(errMessage(e)),
  });

  const createProjectMutation = useMutation({
    mutationFn: async () => {
      // Persist local narration edits first
      if (session) {
        await api.patch(`/clipper/${session.id}/frames`, {
          frames: session.frames.map((f) => ({
            frame_id: f.id,
            selected: f.selected,
            narration: f.narration,
          })),
        });
      }
      const { data } = await api.post(`/clipper/${sessionId}/create-project`, {
        title: title.trim() || "Clipped video lesson",
        description: session ? `Clipped from ${session.filename}` : null,
        generate_tts: generateTts,
      });
      return data as { project_id: string; slide_count: number; tts_enqueued: number };
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["projects-summary"] });
      setSuccess(
        `Created project with ${data.slide_count} slides` +
          (data.tts_enqueued ? ` · ${data.tts_enqueued} voices queued` : "")
      );
      navigate(`/projects/${data.project_id}`);
    },
    onError: (e) => setError(errMessage(e)),
  });

  const estimated = useMemo(() => {
    if (!session) return 0;
    const n = Math.ceil(session.duration_ms / 1000 / Math.max(0.5, intervalS));
    return Math.min(Math.max(1, n), maxFrames);
  }, [session, intervalS, maxFrames]);

  const updateLocalFrame = (id: string, patch: Partial<ClipFrame>) => {
    if (!sessionId || !session) return;
    const next: ClipSession = {
      ...session,
      frames: session.frames.map((f) => (f.id === id ? { ...f, ...patch } : f)),
    };
    next.selected_count = next.frames.filter((f) => f.selected).length;
    qc.setQueryData(["clipper-session", sessionId], next);
  };

  const toggleAll = (selected: boolean) => {
    if (!session) return;
    const updates = session.frames.map((f) => ({ frame_id: f.id, selected }));
    const next: ClipSession = {
      ...session,
      frames: session.frames.map((f) => ({ ...f, selected })),
      selected_count: selected ? session.frames.length : 0,
    };
    qc.setQueryData(["clipper-session", sessionId!], next);
    saveFramesMutation.mutate(updates);
  };

  return (
    <Stack spacing={3}>
      <PageHeader
        title="AI Video Image Clipper"
        subtitle="Upload a video, extract stills as slides, write narration, then generate AI voiceover and export."
        crumbs={[{ label: "Dashboard", to: "/" }, { label: "Clipper" }]}
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

      {/* Step 1: Upload */}
      <Card sx={{ border: "1px solid", borderColor: "divider" }}>
        <CardContent>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <Chip label="1" color="primary" size="small" />
            <Typography variant="h6">Upload source video</Typography>
          </Stack>
          <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>
            MP4 / MOV / WebM / MKV · up to 200&nbsp;MB · max 20 minutes
          </Typography>
          <Button
            variant="contained"
            component="label"
            startIcon={uploading ? <CircularProgress size={18} color="inherit" /> : <CloudUploadIcon />}
            disabled={uploading}
          >
            {uploading ? "Uploading…" : "Choose video"}
            <input
              hidden
              type="file"
              accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.webm,.mkv"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (!file) return;
                setUploading(true);
                setError("");
                uploadMutation.mutate(file);
              }}
            />
          </Button>
          {session && (
            <Stack spacing={1} sx={{ mt: 2 }}>
              <Typography variant="body2">
                <strong>{session.filename}</strong> · {session.duration_label}
              </Typography>
              {session.video_url && (
                <video
                  src={mediaUrl(session.video_url)}
                  controls
                  style={{ width: "100%", maxWidth: 640, borderRadius: 12, background: "#0f172a" }}
                />
              )}
            </Stack>
          )}
        </CardContent>
      </Card>

      {/* Step 2: Extract */}
      <Card sx={{ border: "1px solid", borderColor: "divider", opacity: session ? 1 : 0.55 }}>
        <CardContent>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <Chip label="2" color="primary" size="small" />
            <Typography variant="h6">Extract image clips</Typography>
          </Stack>
          <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>
            Pull still frames on an interval. ~{estimated} frames at current settings (capped at {maxFrames}).
          </Typography>
          <Stack spacing={2} maxWidth={480}>
            <Box>
              <Typography variant="body2" gutterBottom>
                Interval: every {intervalS.toFixed(1)}s
              </Typography>
              <Slider
                value={intervalS}
                min={0.5}
                max={15}
                step={0.5}
                marks={[
                  { value: 1, label: "1s" },
                  { value: 3, label: "3s" },
                  { value: 5, label: "5s" },
                  { value: 10, label: "10s" },
                ]}
                onChange={(_, v) => setIntervalS(v as number)}
                disabled={!session || extractMutation.isPending}
              />
            </Box>
            <Box>
              <Typography variant="body2" gutterBottom>
                Max frames: {maxFrames}
              </Typography>
              <Slider
                value={maxFrames}
                min={1}
                max={50}
                step={1}
                onChange={(_, v) => setMaxFrames(v as number)}
                disabled={!session || extractMutation.isPending}
              />
            </Box>
            <Button
              variant="contained"
              startIcon={
                extractMutation.isPending ? <CircularProgress size={18} color="inherit" /> : <ContentCutIcon />
              }
              disabled={!session || extractMutation.isPending}
              onClick={() => extractMutation.mutate()}
            >
              {extractMutation.isPending ? "Extracting…" : "Extract frames"}
            </Button>
            {extractMutation.isPending && <LinearProgress />}
          </Stack>
        </CardContent>
      </Card>

      {/* Step 3: Select + narrate */}
      <Card sx={{ border: "1px solid", borderColor: "divider", opacity: frames.length ? 1 : 0.55 }}>
        <CardContent>
          <Stack
            direction={{ xs: "column", sm: "row" }}
            justifyContent="space-between"
            alignItems={{ sm: "center" }}
            spacing={1}
            sx={{ mb: 2 }}
          >
            <Stack direction="row" spacing={1} alignItems="center">
              <Chip label="3" color="primary" size="small" />
              <Typography variant="h6">Select clips & add voiceover scripts</Typography>
            </Stack>
            <Stack direction="row" spacing={1}>
              <Button
                size="small"
                startIcon={<SelectAllIcon />}
                disabled={!frames.length}
                onClick={() => toggleAll(true)}
              >
                Select all
              </Button>
              <Button
                size="small"
                startIcon={<DeselectIcon />}
                disabled={!frames.length}
                onClick={() => toggleAll(false)}
              >
                Deselect all
              </Button>
            </Stack>
          </Stack>
          <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>
            {frames.length
              ? `${selectedCount} of ${frames.length} selected · write narration under each frame for AI voiceover`
              : "Extract frames to continue"}
          </Typography>

          <Box
            display="grid"
            gap={2}
            gridTemplateColumns={{ xs: "1fr", sm: "1fr 1fr", lg: "1fr 1fr 1fr" }}
          >
            {frames.map((f, idx) => (
              <Card
                key={f.id}
                variant="outlined"
                sx={{
                  borderColor: f.selected ? "primary.main" : "divider",
                  borderWidth: f.selected ? 2 : 1,
                }}
              >
                <Box
                  component="img"
                  src={mediaUrl(f.image_url)}
                  alt={`Frame ${idx + 1}`}
                  sx={{
                    width: "100%",
                    height: 160,
                    objectFit: "cover",
                    bgcolor: "#0f172a",
                    display: "block",
                  }}
                />
                <CardContent>
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={f.selected}
                          onChange={(e) => {
                            updateLocalFrame(f.id, { selected: e.target.checked });
                            saveFramesMutation.mutate([
                              { frame_id: f.id, selected: e.target.checked },
                            ]);
                          }}
                        />
                      }
                      label={`Clip ${idx + 1}`}
                    />
                    <Chip size="small" label={f.time_label} />
                  </Stack>
                  <TextField
                    fullWidth
                    size="small"
                    multiline
                    minRows={2}
                    placeholder="Narration / voiceover script for this clip…"
                    value={f.narration}
                    disabled={!f.selected}
                    onChange={(e) => updateLocalFrame(f.id, { narration: e.target.value })}
                    onBlur={() =>
                      saveFramesMutation.mutate([{ frame_id: f.id, narration: f.narration }])
                    }
                  />
                </CardContent>
              </Card>
            ))}
          </Box>
        </CardContent>
      </Card>

      {/* Step 4: Create project + voice */}
      <Card sx={{ border: "1px solid", borderColor: "divider", opacity: selectedCount ? 1 : 0.55 }}>
        <CardContent>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <Chip label="4" color="primary" size="small" />
            <Typography variant="h6">Create project & add AI voiceover</Typography>
          </Stack>
          <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>
            Creates a normal project from selected clips. You can refine narration, generate voices, and export MP4
            in the editor — same pipeline as manual projects.
          </Typography>
          <Stack spacing={2} maxWidth={520}>
            <TextField
              label="Project title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              fullWidth
              disabled={!selectedCount}
            />
            <FormControlLabel
              control={
                <Switch
                  checked={generateTts}
                  onChange={(e) => setGenerateTts(e.target.checked)}
                  disabled={!selectedCount}
                />
              }
              label="Queue AI voiceover now for clips that have narration text"
            />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <Button
                variant="contained"
                size="large"
                startIcon={
                  createProjectMutation.isPending ? (
                    <CircularProgress size={18} color="inherit" />
                  ) : (
                    <MovieCreationIcon />
                  )
                }
                disabled={!selectedCount || createProjectMutation.isPending || !title.trim()}
                onClick={() => createProjectMutation.mutate()}
              >
                {createProjectMutation.isPending
                  ? "Creating…"
                  : `Create project (${selectedCount} slides)`}
              </Button>
              <Button
                variant="outlined"
                startIcon={<RecordVoiceOverIcon />}
                disabled={!selectedCount || createProjectMutation.isPending}
                onClick={() => {
                  setGenerateTts(true);
                  createProjectMutation.mutate();
                }}
              >
                Create + generate voices
              </Button>
            </Stack>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
