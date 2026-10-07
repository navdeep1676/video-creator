import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link as RouterLink, useParams, useSearchParams } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Collapse,
  FormControl,
  FormControlLabel,
  InputLabel,
  LinearProgress,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  MenuItem,
  Select,
  Stack,
  Switch,
  Typography,
} from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import StopIcon from "@mui/icons-material/Stop";
import SpeedIcon from "@mui/icons-material/Speed";
import HighQualityIcon from "@mui/icons-material/HighQuality";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import ErrorOutlineRoundedIcon from "@mui/icons-material/ErrorOutlineRounded";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";
import SubtitlesOutlinedIcon from "@mui/icons-material/SubtitlesOutlined";
import YouTubeIcon from "@mui/icons-material/YouTube";
import SmartDisplayOutlinedIcon from "@mui/icons-material/SmartDisplayOutlined";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import RefreshIcon from "@mui/icons-material/Refresh";
import ChecklistRtlIcon from "@mui/icons-material/ChecklistRtl";
import VideoLibraryIcon from "@mui/icons-material/VideoLibrary";
import Filter1Icon from "@mui/icons-material/Filter1";
import { api, errMessage, mediaUrl } from "../api/client";
import PageHeader from "../components/PageHeader";
import type { Project } from "../types/project";
import { getAspectOption } from "../types/aspectRatio";
import { brandColors } from "../theme";

type Job = {
  id: string;
  status: string;
  progress: number;
  stage: string | null;
  video_url: string | null;
  thumbnail_url: string | null;
  duration_ms: number | null;
  aspect_ratio?: string | null;
  width?: number | null;
  height?: number | null;
  quality?: string | null;
  caption_style?: string | null;
  slide_id?: string | null;
  slide_order?: number | null;
  error_code: string | null;
  error_message: string | null;
};

type QualityId = "draft" | "full";
type CaptionStyleId = "auto" | "youtube" | "shorts";
type RenderScope = "all" | "one";

type ExportSlide = {
  id: string;
  order_index: number;
  narration?: { text?: string | null } | null;
};

type ExportCheckIssue = {
  slide_id?: string | null;
  order?: number | null;
  message: string;
};

type ExportCheckItem = {
  id: string;
  ok: boolean;
  label: string;
  severity: string;
  count: number;
  issues: ExportCheckIssue[];
};

type ExportReadiness = {
  ready: boolean;
  project_id: string;
  slide_count: number;
  summary: {
    missing_images: number;
    empty_narration: number;
    missing_tts: number;
    tts_in_progress: number;
  };
  checks: ExportCheckItem[];
  recommended_caption_style: string;
};

type CaptionStyle = {
  id: CaptionStyleId;
  label: string;
  description: string;
  margin_v_ratio: number;
  margin_h_ratio: number;
  font_scale: number;
  max_chars: number;
  max_words: number;
  best_for: string[];
};

function slideLabel(slide: ExportSlide): string {
  const text = (slide.narration?.text || "").replace(/\s+/g, " ").trim();
  const preview = text.length > 42 ? `${text.slice(0, 42)}…` : text;
  return preview ? `Slide ${slide.order_index + 1} — ${preview}` : `Slide ${slide.order_index + 1}`;
}

function jobScopeLabel(job: Job): string {
  if (job.slide_order) return `Slide ${job.slide_order}`;
  if (job.slide_id) return "One slide";
  return "All slides";
}

function draftCanvas(w: number, h: number): { width: number; height: number } {
  const short = Math.min(w, h);
  const scale = 720 / short;
  return {
    width: Math.max(2, Math.round((w * scale) / 2) * 2),
    height: Math.max(2, Math.round((h * scale) / 2) * 2),
  };
}

function CheckStatusIcon({ ok, severity }: { ok: boolean; severity: string }) {
  if (ok) return <CheckCircleRoundedIcon sx={{ color: "#10B981" }} />;
  if (severity === "warning") return <WarningAmberRoundedIcon sx={{ color: "#F59E0B" }} />;
  return <ErrorOutlineRoundedIcon sx={{ color: brandColors.rose }} />;
}

const CAPTION_ICONS: Record<CaptionStyleId, React.ReactNode> = {
  auto: <AutoAwesomeIcon color="primary" />,
  youtube: <YouTubeIcon color="primary" />,
  shorts: <SmartDisplayOutlinedIcon color="primary" />,
};

export default function ExportPage() {
  const { projectId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const qc = useQueryClient();
  const requestedSlide = searchParams.get("slide");
  const [jobId, setJobId] = useState<string | null>(null);
  const [scope, setScope] = useState<RenderScope>(requestedSlide ? "one" : "all");
  const [slideId, setSlideId] = useState(requestedSlide || "");
  const [includeSubtitles, setIncludeSubtitles] = useState(true);
  const [captionStyle, setCaptionStyle] = useState<CaptionStyleId>("auto");
  const [quality, setQuality] = useState<QualityId>("full");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [expandedCheck, setExpandedCheck] = useState<string | null>(null);
  const [captionDefaulted, setCaptionDefaulted] = useState(false);

  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    enabled: !!jobId,
    queryFn: async () => (await api.get(`/video/status/${jobId}`)).data as Job,
    refetchInterval: (q) => {
      const st = q.state.data?.status;
      return st === "queued" || st === "processing" ? 1500 : false;
    },
  });

  const historyQuery = useQuery({
    queryKey: ["videos", projectId],
    queryFn: async () => (await api.get(`/video/projects/${projectId}/videos`)).data as { items: Job[] },
  });

  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: async () => (await api.get(`/projects/${projectId}`)).data as Project,
  });

  const slidesQuery = useQuery({
    queryKey: ["slides", projectId],
    queryFn: async () => (await api.get(`/projects/${projectId}/slides`)).data as ExportSlide[],
  });

  const storyMusicQuery = useQuery({
    queryKey: ["story", projectId],
    queryFn: async () =>
      (await api.get(`/projects/${projectId}/story`)).data as {
        music?: { audio_url: string | null };
        settings?: { music_mode?: string; duration_seconds?: number } | null;
      },
  });

  const slides = slidesQuery.data || [];
  const renderSlideId = scope === "one" ? slideId || null : null;

  const readinessQuery = useQuery({
    queryKey: ["export-readiness", projectId, renderSlideId],
    enabled: scope === "all" || !!renderSlideId,
    queryFn: async () =>
      (
        await api.get(`/video/projects/${projectId}/export-readiness`, {
          params: renderSlideId ? { slide_id: renderSlideId } : {},
        })
      ).data as ExportReadiness,
    refetchInterval: (q) => {
      const data = q.state.data;
      if (!data) return 4000;
      if (data.summary.tts_in_progress > 0) return 2500;
      return false;
    },
  });

  const captionStylesQuery = useQuery({
    queryKey: ["caption-styles"],
    queryFn: async () => {
      const { data } = await api.get("/video/caption-styles");
      return (data.items || []) as CaptionStyle[];
    },
  });

  const aspect = getAspectOption(projectQuery.data?.aspect_ratio);
  const canvasW = projectQuery.data?.canvas_width || aspect.width;
  const canvasH = projectQuery.data?.canvas_height || aspect.height;
  const draftSize = useMemo(() => draftCanvas(canvasW, canvasH), [canvasW, canvasH]);
  const exportSize = quality === "draft" ? draftSize : { width: canvasW, height: canvasH };

  const readiness = readinessQuery.data;
  const exportReady = !!readiness?.ready;
  const selectedSlide = slides.find((s) => s.id === slideId) || null;

  useEffect(() => {
    if (!slides.length) return;
    if (slideId && slides.some((s) => s.id === slideId)) return;
    const fromUrl =
      requestedSlide && slides.some((s) => s.id === requestedSlide) ? requestedSlide : slides[0].id;
    setSlideId(fromUrl);
  }, [slides, slideId, requestedSlide]);

  // Prefer recommended caption style once readiness loads
  useEffect(() => {
    if (captionDefaulted || !readiness?.recommended_caption_style) return;
    const rec = readiness.recommended_caption_style as CaptionStyleId;
    if (rec === "youtube" || rec === "shorts") {
      setCaptionStyle(rec);
      setCaptionDefaulted(true);
    }
  }, [readiness?.recommended_caption_style, captionDefaulted]);

  const renderMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post("/video/render", {
        project_id: projectId,
        slide_id: renderSlideId,
        include_subtitles: includeSubtitles,
        caption_style: includeSubtitles ? captionStyle : "auto",
        aspect_ratio: aspect.id,
        quality,
      });
      return data as Job;
    },
    onSuccess: (job) => {
      setJobId(job.id);
      setError("");
      setSuccess("");
      qc.invalidateQueries({ queryKey: ["export-readiness", projectId] });
      qc.invalidateQueries({ queryKey: ["videos", projectId] });
    },
    onError: (e) => setError(errMessage(e)),
  });

  const stopMutation = useMutation({
    mutationFn: async () => {
      if (jobId) {
        return (await api.post(`/video/jobs/${jobId}/cancel`)).data as Job;
      }
      return (await api.post(`/video/projects/${projectId}/stop`)).data as {
        cancelled_tts: number;
        cancelled_renders: number;
      };
    },
    onSuccess: (data) => {
      setError("");
      if (data && "status" in data) {
        qc.setQueryData(["job", jobId], data);
        setSuccess("Render stopped");
      } else {
        setSuccess("Stopped running jobs");
      }
      qc.invalidateQueries({ queryKey: ["job", jobId] });
      qc.invalidateQueries({ queryKey: ["videos", projectId] });
      qc.invalidateQueries({ queryKey: ["export-readiness", projectId] });
    },
    onError: (e) => setError(errMessage(e)),
  });

  const job = jobQuery.data;
  const jobRunning = job?.status === "queued" || job?.status === "processing";
  const previewMaxWidth =
    aspect.id === "9:16" || aspect.id === "4:5" ? 320 : aspect.id === "1:1" ? 420 : 720;

  const captionPacks: CaptionStyle[] =
    captionStylesQuery.data && captionStylesQuery.data.length > 0
      ? captionStylesQuery.data
      : [
          {
            id: "auto",
            label: "Auto (by format)",
            description: "YouTube safe for landscape; Shorts safe for portrait.",
            margin_v_ratio: 0.09,
            margin_h_ratio: 0.055,
            font_scale: 1,
            max_chars: 42,
            max_words: 7,
            best_for: ["any"],
          },
          {
            id: "youtube",
            label: "YouTube safe",
            description: "Lower-third captions with side margins for long-form players.",
            margin_v_ratio: 0.09,
            margin_h_ratio: 0.055,
            font_scale: 1,
            max_chars: 42,
            max_words: 7,
            best_for: ["long"],
          },
          {
            id: "shorts",
            label: "Shorts safe",
            description: "Extra bottom & side margins clear of Shorts / Reels UI chrome.",
            margin_v_ratio: 0.2,
            margin_h_ratio: 0.11,
            font_scale: 1.12,
            max_chars: 28,
            max_words: 5,
            best_for: ["short"],
          },
        ];

  const selectedPack = captionPacks.find((p) => p.id === captionStyle) || captionPacks[0];

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Export video"
        subtitle={`Renders as ${aspect.label} — checklist, caption style, then draft or full quality.`}
        crumbs={[
          { label: "Dashboard", to: "/dashboard" },
          { label: "Projects", to: "/projects" },
          { label: projectQuery.data?.title || "Project", to: `/projects/${projectId}` },
          { label: "Export" },
        ]}
        actions={
          <Button component={RouterLink} to={`/projects/${projectId}`} variant="outlined">
            Back to editor
          </Button>
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

      {/* Export checklist */}
      <Card>
        <CardContent>
          <Stack
            direction={{ xs: "column", sm: "row" }}
            justifyContent="space-between"
            alignItems={{ xs: "stretch", sm: "flex-start" }}
            spacing={1.5}
            sx={{ mb: 2 }}
          >
            <Box>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                <ChecklistRtlIcon color="primary" />
                <Typography variant="h6" fontWeight={800}>
                  Export checklist
                </Typography>
                {readiness && (
                  <Chip
                    size="small"
                    color={exportReady ? "success" : "warning"}
                    label={exportReady ? "Ready to render" : "Fix issues first"}
                    sx={{ fontWeight: 700 }}
                  />
                )}
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {scope === "one"
                  ? "Checks this slide’s image, narration, and voice before a single-slide video."
                  : "Checks missing images, empty narration, and TTS status before you start a render."}
              </Typography>
            </Box>
            <Button
              size="small"
              startIcon={<RefreshIcon />}
              onClick={() => readinessQuery.refetch()}
              disabled={readinessQuery.isFetching}
            >
              Refresh
            </Button>
          </Stack>

          {readinessQuery.isLoading && <LinearProgress sx={{ mb: 2 }} />}

          {readinessQuery.isError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {errMessage(readinessQuery.error)}
            </Alert>
          )}

          {readiness && (
            <>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
                <Chip
                  size="small"
                  variant="outlined"
                  label={
                    scope === "one"
                      ? selectedSlide
                        ? `Slide ${selectedSlide.order_index + 1} only`
                        : "One slide"
                      : `${readiness.slide_count} slides`
                  }
                />
                <Chip
                  size="small"
                  color={readiness.summary.missing_images ? "error" : "default"}
                  variant="outlined"
                  label={`${readiness.summary.missing_images} missing images`}
                />
                <Chip
                  size="small"
                  color={readiness.summary.empty_narration ? "error" : "default"}
                  variant="outlined"
                  label={`${readiness.summary.empty_narration} empty narration`}
                />
                <Chip
                  size="small"
                  color={readiness.summary.missing_tts ? "error" : "default"}
                  variant="outlined"
                  label={`${readiness.summary.missing_tts} missing TTS`}
                />
                {readiness.summary.tts_in_progress > 0 && (
                  <Chip
                    size="small"
                    color="warning"
                    label={`${readiness.summary.tts_in_progress} TTS in progress`}
                  />
                )}
              </Stack>

              <List dense disablePadding>
                {readiness.checks.map((c) => {
                  const open = expandedCheck === c.id;
                  const hasIssues = c.issues.length > 0;
                  return (
                    <Box key={c.id} sx={{ mb: 0.75 }}>
                      <ListItem
                        onClick={() => hasIssues && setExpandedCheck(open ? null : c.id)}
                        sx={{
                          border: "1px solid",
                          borderColor: c.ok ? "divider" : c.severity === "warning" ? "warning.light" : "error.light",
                          borderRadius: 2,
                          bgcolor: c.ok
                            ? "rgba(16,185,129,0.04)"
                            : c.severity === "warning"
                              ? "rgba(245,158,11,0.06)"
                              : "rgba(244,63,94,0.05)",
                          cursor: hasIssues ? "pointer" : "default",
                          py: 1,
                        }}
                      >
                        <ListItemIcon sx={{ minWidth: 40 }}>
                          <CheckStatusIcon ok={c.ok} severity={c.severity} />
                        </ListItemIcon>
                        <ListItemText
                          primary={c.label}
                          secondary={
                            c.ok
                              ? "Passed"
                              : `${c.count} issue${c.count === 1 ? "" : "s"}${hasIssues ? " · tap to expand" : ""}`
                          }
                          primaryTypographyProps={{ fontWeight: 700 }}
                        />
                      </ListItem>
                      <Collapse in={open && hasIssues}>
                        <Box sx={{ pl: 6, pr: 1, py: 1 }}>
                          {c.issues.map((iss, idx) => (
                            <Typography
                              key={`${c.id}-${idx}`}
                              variant="body2"
                              color="text.secondary"
                              sx={{ py: 0.25 }}
                            >
                              · {iss.message}
                            </Typography>
                          ))}
                          {!c.ok && (
                            <Button
                              component={RouterLink}
                              to={`/projects/${projectId}`}
                              size="small"
                              sx={{ mt: 1 }}
                            >
                              Open project editor
                            </Button>
                          )}
                        </Box>
                      </Collapse>
                    </Box>
                  );
                })}
              </List>

              {!exportReady && (
                <Alert severity="warning" sx={{ mt: 2 }}>
                  Resolve checklist issues before generating a video. Incomplete slides are blocked on
                  the server as well.
                </Alert>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Stack spacing={2.5}>
            <Box>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                Project format
              </Typography>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <Chip color="primary" label={aspect.label} />
                <Chip variant="outlined" label={`${canvasW}×${canvasH} full`} />
              </Stack>
            </Box>

            <Box>
              <Typography variant="subtitle1" fontWeight={700} gutterBottom>
                What to render
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                A full video joins every slide. A single-slide video exports only the slide you pick.
              </Typography>
              <Box
                sx={{
                  display: "grid",
                  gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
                  gap: 1.5,
                }}
              >
                {(
                  [
                    {
                      id: "all" as const,
                      title: "Full video",
                      body: "Every slide, in order, as one MP4.",
                      icon: <VideoLibraryIcon color="primary" />,
                    },
                    {
                      id: "one" as const,
                      title: "One slide",
                      body: "Render a single slide as its own video.",
                      icon: <Filter1Icon color="primary" />,
                    },
                  ] as const
                ).map((opt) => {
                  const selected = scope === opt.id;
                  return (
                    <Card
                      key={opt.id}
                      variant="outlined"
                      sx={{
                        borderColor: selected ? "primary.main" : "divider",
                        borderWidth: selected ? 2 : 1,
                        bgcolor: selected ? "action.selected" : "background.paper",
                      }}
                    >
                      <CardActionArea
                        onClick={() => setScope(opt.id)}
                        disabled={jobRunning}
                        sx={{ height: "100%" }}
                      >
                        <CardContent sx={{ display: "flex", gap: 1.5, alignItems: "flex-start" }}>
                          {opt.icon}
                          <Box>
                            <Typography variant="body1" fontWeight={700}>
                              {opt.title}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {opt.body}
                            </Typography>
                          </Box>
                        </CardContent>
                      </CardActionArea>
                    </Card>
                  );
                })}
              </Box>
              {scope === "one" && (
                <FormControl fullWidth sx={{ mt: 1.5 }} disabled={jobRunning || slides.length === 0}>
                  <InputLabel id="export-slide-label">Slide</InputLabel>
                  <Select
                    labelId="export-slide-label"
                    label="Slide"
                    value={slides.some((s) => s.id === slideId) ? slideId : ""}
                    onChange={(e) => setSlideId(e.target.value)}
                  >
                    {slides.map((s) => (
                      <MenuItem key={s.id} value={s.id}>
                        {slideLabel(s)}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              )}
            </Box>

            <Box>
              <Typography variant="subtitle1" fontWeight={700} gutterBottom>
                Quality
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Draft is faster and smaller — great for checking timing before a full export.
              </Typography>
              <Box
                sx={{
                  display: "grid",
                  gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
                  gap: 1.5,
                }}
              >
                {(
                  [
                    {
                      id: "draft" as const,
                      title: "Draft 720p",
                      body: `${draftSize.width}×${draftSize.height} · faster encode · smaller file`,
                      icon: <SpeedIcon color="primary" />,
                    },
                    {
                      id: "full" as const,
                      title: "Full quality",
                      body: `${canvasW}×${canvasH} · sharper · delivery ready`,
                      icon: <HighQualityIcon color="primary" />,
                    },
                  ] as const
                ).map((opt) => {
                  const selected = quality === opt.id;
                  return (
                    <Card
                      key={opt.id}
                      variant="outlined"
                      sx={{
                        borderColor: selected ? "primary.main" : "divider",
                        borderWidth: selected ? 2 : 1,
                        bgcolor: selected ? "action.selected" : "background.paper",
                      }}
                    >
                      <CardActionArea
                        onClick={() => setQuality(opt.id)}
                        disabled={jobRunning}
                        sx={{ height: "100%" }}
                      >
                        <CardContent sx={{ display: "flex", gap: 1.5, alignItems: "flex-start" }}>
                          {opt.icon}
                          <Box>
                            <Typography variant="body1" fontWeight={700}>
                              {opt.title}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {opt.body}
                            </Typography>
                          </Box>
                        </CardContent>
                      </CardActionArea>
                    </Card>
                  );
                })}
              </Box>
            </Box>

            <FormControlLabel
              control={
                <Switch
                  checked={includeSubtitles}
                  onChange={(e) => setIncludeSubtitles(e.target.checked)}
                  disabled={jobRunning}
                />
              }
              label={
                <Stack direction="row" spacing={0.75} alignItems="center">
                  <SubtitlesOutlinedIcon fontSize="small" color="action" />
                  <span>Burn in captions (timed to voice)</span>
                </Stack>
              }
            />

            {includeSubtitles && (
              <Box>
                <Typography variant="subtitle1" fontWeight={700} gutterBottom>
                  Captions style pack
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                  Platform-safe margins so text stays clear of YouTube chrome or Shorts / Reels UI.
                  {readiness?.recommended_caption_style
                    ? ` Recommended for this project: ${readiness.recommended_caption_style}.`
                    : ""}
                </Typography>
                <Box
                  sx={{
                    display: "grid",
                    gridTemplateColumns: { xs: "1fr", md: "1fr 1fr 1fr" },
                    gap: 1.5,
                  }}
                >
                  {captionPacks.map((pack) => {
                    const selected = captionStyle === pack.id;
                    return (
                      <Card
                        key={pack.id}
                        variant="outlined"
                        sx={{
                          borderColor: selected ? "primary.main" : "divider",
                          borderWidth: selected ? 2 : 1,
                          bgcolor: selected ? "action.selected" : "background.paper",
                          opacity: jobRunning ? 0.7 : 1,
                        }}
                      >
                        <CardActionArea
                          onClick={() => setCaptionStyle(pack.id)}
                          disabled={jobRunning}
                          sx={{ height: "100%" }}
                        >
                          <CardContent>
                            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                              {CAPTION_ICONS[pack.id] || <SubtitlesOutlinedIcon color="primary" />}
                              <Typography variant="body1" fontWeight={700}>
                                {pack.label}
                              </Typography>
                            </Stack>
                            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.25 }}>
                              {pack.description}
                            </Typography>
                            {/* Safe-area preview */}
                            <Box
                              sx={{
                                position: "relative",
                                width: "100%",
                                aspectRatio:
                                  aspect.id === "9:16" || aspect.id === "4:5"
                                    ? "9 / 16"
                                    : aspect.id === "1:1"
                                      ? "1 / 1"
                                      : "16 / 9",
                                maxHeight: 120,
                                mx: "auto",
                                borderRadius: 1.5,
                                bgcolor: "rgba(15,23,42,0.88)",
                                overflow: "hidden",
                                border: "1px solid",
                                borderColor: "divider",
                              }}
                            >
                              {/* Safe margin guides */}
                              <Box
                                sx={{
                                  position: "absolute",
                                  left: `${pack.margin_h_ratio * 100}%`,
                                  right: `${pack.margin_h_ratio * 100}%`,
                                  bottom: `${pack.margin_v_ratio * 100}%`,
                                  height: 10,
                                  borderRadius: 0.5,
                                  background: selected
                                    ? `linear-gradient(90deg, ${brandColors.violet}, ${brandColors.cyan})`
                                    : "rgba(255,255,255,0.55)",
                                }}
                              />
                              <Typography
                                variant="caption"
                                sx={{
                                  position: "absolute",
                                  bottom: 4,
                                  left: 0,
                                  right: 0,
                                  textAlign: "center",
                                  color: "rgba(248,250,252,0.55)",
                                  fontSize: 9,
                                  fontWeight: 700,
                                }}
                              >
                                bottom {(pack.margin_v_ratio * 100).toFixed(0)}% · sides{" "}
                                {(pack.margin_h_ratio * 100).toFixed(0)}%
                              </Typography>
                            </Box>
                          </CardContent>
                        </CardActionArea>
                      </Card>
                    );
                  })}
                </Box>
                {selectedPack && (
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 1.25, display: "block" }}>
                    Pack uses ~{Math.round(selectedPack.font_scale * 100)}% type scale · cue length guide{" "}
                    {selectedPack.max_chars} chars / {selectedPack.max_words} words
                  </Typography>
                )}
              </Box>
            )}

            {storyMusicQuery.data?.music?.audio_url && storyMusicQuery.data?.settings?.music_mode !== "none" && (
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                {scope === "one"
                  ? "Generated music is mixed under this slide and trimmed to its length, starting from the beginning of the track."
                  : "Generated music is mixed under the narration for the full video. Scene length stays at the story plan when the spoken line is shorter, so the picture and the music end together."}
              </Typography>
            )}

            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Button
                variant="contained"
                size="large"
                disabled={
                  renderMutation.isPending || jobRunning || !exportReady || (scope === "one" && !renderSlideId)
                }
                onClick={() => renderMutation.mutate()}
              >
                {!exportReady
                  ? "Fix checklist to generate"
                  : scope === "one"
                    ? `Generate slide ${selectedSlide ? selectedSlide.order_index + 1 : ""} (${exportSize.width}×${exportSize.height})`
                    : quality === "draft"
                      ? `Generate draft (${exportSize.width}×${exportSize.height})`
                      : `Generate full video (${exportSize.width}×${exportSize.height})`}
              </Button>
              <Button
                variant="outlined"
                color="error"
                size="large"
                startIcon={<StopIcon />}
                disabled={stopMutation.isPending || !jobRunning}
                onClick={() => stopMutation.mutate()}
              >
                {stopMutation.isPending ? "Stopping…" : "Stop render"}
              </Button>
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Rendering runs in a background worker. Captions use the selected style pack when burn-in is
              enabled.
            </Typography>
          </Stack>
        </CardContent>
      </Card>

      {job && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Current job
            </Typography>
            <Typography variant="body2" gutterBottom>
              Status: <strong>{job.status}</strong>
              {job.stage ? ` · stage: ${job.stage}` : ""}
              {job.quality ? ` · ${job.quality}` : ""}
              {job.caption_style ? ` · captions: ${job.caption_style}` : ""}
              {` · ${jobScopeLabel(job)}`}
              {job.aspect_ratio
                ? ` · ${job.aspect_ratio}${job.width && job.height ? ` (${job.width}×${job.height})` : ""}`
                : ""}
            </Typography>
            {jobRunning && (
              <Box sx={{ my: 2 }}>
                <LinearProgress
                  variant={job.progress > 0 ? "determinate" : "indeterminate"}
                  value={job.progress}
                />
                <Typography variant="caption">{job.progress}%</Typography>
              </Box>
            )}
            {job.status === "cancelled" && <Alert severity="warning">Render was stopped.</Alert>}
            {job.status === "failed" && (
              <Alert severity="error">
                {job.error_code}: {job.error_message}
              </Alert>
            )}
            {job.status === "completed" && (
              <Stack spacing={2}>
                {job.thumbnail_url && (
                  <Box
                    component="img"
                    src={mediaUrl(job.thumbnail_url)}
                    alt="Thumbnail"
                    sx={{ maxWidth: previewMaxWidth, width: "100%", borderRadius: 2 }}
                  />
                )}
                {job.video_url && (
                  <video
                    controls
                    src={mediaUrl(job.video_url)}
                    style={{ width: "100%", maxWidth: previewMaxWidth, borderRadius: 12 }}
                  />
                )}
                <Button
                  variant="contained"
                  startIcon={<DownloadIcon />}
                  href={`/api/v1/video/download/${job.id}`}
                  onClick={async (e) => {
                    e.preventDefault();
                    const res = await api.get(`/video/download/${job.id}`, { responseType: "blob" });
                    const url = URL.createObjectURL(res.data);
                    const a = document.createElement("a");
                    a.href = url;
                    const ratioTag = job.aspect_ratio ? `-${job.aspect_ratio.replace(":", "x")}` : "";
                    const qTag = job.quality === "draft" ? "-draft" : "";
                    const slideTag = job.slide_order ? `-slide${job.slide_order}` : "";
                    a.download = `video${slideTag}${ratioTag}${qTag}-${job.id.slice(0, 8)}.mp4`;
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                >
                  Download MP4
                </Button>
                {job.duration_ms && (
                  <Typography variant="body2" color="text.secondary">
                    Duration: {(job.duration_ms / 1000).toFixed(1)}s
                  </Typography>
                )}
              </Stack>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Recent renders
          </Typography>
          <Stack spacing={1}>
            {(historyQuery.data?.items || []).map((j) => (
              <Box
                key={j.id}
                sx={{
                  p: 1.5,
                  border: "1px solid",
                  borderColor: "divider",
                  borderRadius: 2,
                  cursor: "pointer",
                }}
                onClick={() => setJobId(j.id)}
              >
                <Typography variant="body2">
                  {j.id.slice(0, 8)}… · {j.status} · {j.progress}%
                  {j.quality ? ` · ${j.quality}` : ""}
                  {` · ${jobScopeLabel(j)}`}
                  {j.caption_style ? ` · ${j.caption_style}` : ""}
                  {j.aspect_ratio
                    ? ` · ${j.aspect_ratio}${j.width && j.height ? ` ${j.width}×${j.height}` : ""}`
                    : ""}
                </Typography>
              </Box>
            ))}
            {(historyQuery.data?.items || []).length === 0 && (
              <Typography color="text.secondary" variant="body2">
                No renders yet.
              </Typography>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
