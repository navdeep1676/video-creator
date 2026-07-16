import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link as RouterLink, useParams } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  FormControlLabel,
  LinearProgress,
  Stack,
  Switch,
  Typography,
} from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import StopIcon from "@mui/icons-material/Stop";
import { api, errMessage, mediaUrl } from "../api/client";
import PageHeader from "../components/PageHeader";
import type { Project } from "../types/project";

type Job = {
  id: string;
  status: string;
  progress: number;
  stage: string | null;
  video_url: string | null;
  thumbnail_url: string | null;
  duration_ms: number | null;
  error_code: string | null;
  error_message: string | null;
};

export default function ExportPage() {
  const { projectId = "" } = useParams();
  const qc = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [includeSubtitles, setIncludeSubtitles] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

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

  const renderMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post("/video/render", {
        project_id: projectId,
        include_subtitles: includeSubtitles,
      });
      return data as Job;
    },
    onSuccess: (job) => {
      setJobId(job.id);
      setError("");
      setSuccess("");
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
    },
    onError: (e) => setError(errMessage(e)),
  });

  const job = jobQuery.data;
  const jobRunning = job?.status === "queued" || job?.status === "processing";

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Export video"
        subtitle="Render an MP4 with narration, Ken Burns motion, fades, and optional subtitles."
        crumbs={[
          { label: "Dashboard", to: "/" },
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

      <Card>
        <CardContent>
          <Stack spacing={2}>
            <FormControlLabel
              control={<Switch checked={includeSubtitles} onChange={(e) => setIncludeSubtitles(e.target.checked)} />}
              label="Burn in subtitles (timed to voice)"
            />
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Button
                variant="contained"
                size="large"
                disabled={renderMutation.isPending || jobRunning}
                onClick={() => renderMutation.mutate()}
              >
                Generate video
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
              Requires narration text and ready TTS audio on every slide. Rendering runs in a background worker.
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
            </Typography>
            {jobRunning && (
              <Box sx={{ my: 2 }}>
                <LinearProgress variant={job.progress > 0 ? "determinate" : "indeterminate"} value={job.progress} />
                <Typography variant="caption">{job.progress}%</Typography>
              </Box>
            )}
            {job.status === "cancelled" && (
              <Alert severity="warning">Render was stopped.</Alert>
            )}
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
                    sx={{ maxWidth: 480, width: "100%", borderRadius: 2 }}
                  />
                )}
                {job.video_url && (
                  <video controls src={mediaUrl(job.video_url)} style={{ width: "100%", maxWidth: 720, borderRadius: 12 }} />
                )}
                <Button
                  variant="contained"
                  startIcon={<DownloadIcon />}
                  href={`/api/v1/video/download/${job.id}`}
                  // download uses bearer via new tab won't work — use fetch
                  onClick={async (e) => {
                    e.preventDefault();
                    const res = await api.get(`/video/download/${job.id}`, { responseType: "blob" });
                    const url = URL.createObjectURL(res.data);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `video-${job.id}.mp4`;
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
                sx={{ p: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 2, cursor: "pointer" }}
                onClick={() => setJobId(j.id)}
              >
                <Typography variant="body2">
                  {j.id.slice(0, 8)}… · {j.status} · {j.progress}%
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
