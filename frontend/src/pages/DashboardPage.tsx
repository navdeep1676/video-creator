import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import CollectionsIcon from "@mui/icons-material/Collections";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";
import MovieCreationIcon from "@mui/icons-material/MovieCreation";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import { api, errMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import PageHeader from "../components/PageHeader";
import ProjectCard from "../components/ProjectCard";
import ProjectFormDialog, { type ProjectFormValues } from "../components/ProjectFormDialog";
import type { Project, ProjectListResponse, ProjectSummary } from "../types/project";

function StatCard({
  label,
  value,
  icon,
  color,
}: {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  color: string;
}) {
  return (
    <Card sx={{ height: "100%", border: "1px solid", borderColor: "divider" }}>
      <CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
          <Box>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              {label}
            </Typography>
            <Typography variant="h4">{value}</Typography>
          </Box>
          <Box
            sx={{
              width: 44,
              height: 44,
              borderRadius: 2,
              display: "grid",
              placeItems: "center",
              bgcolor: color,
              color: "#fff",
            }}
          >
            {icon}
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [createOpen, setCreateOpen] = useState(false);
  const [editProject, setEditProject] = useState<Project | null>(null);
  const [formError, setFormError] = useState("");

  const summaryQuery = useQuery({
    queryKey: ["projects-summary"],
    queryFn: async () => (await api.get("/projects/summary")).data as ProjectSummary,
  });

  const recentQuery = useQuery({
    queryKey: ["projects", "recent"],
    queryFn: async () => {
      const { data } = await api.get("/projects", { params: { status: "draft", limit: 6 } });
      return data as ProjectListResponse;
    },
  });

  const createMutation = useMutation({
    mutationFn: async (values: ProjectFormValues) => {
      const { data } = await api.post("/projects", {
        title: values.title,
        description: values.description || null,
      });
      return data as Project;
    },
    onSuccess: (project) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["projects-summary"] });
      setCreateOpen(false);
      navigate(`/projects/${project.id}`);
    },
    onError: (e) => setFormError(errMessage(e)),
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, values }: { id: string; values: ProjectFormValues }) => {
      const { data } = await api.patch(`/projects/${id}`, {
        title: values.title,
        description: values.description || null,
        status: values.status,
      });
      return data as Project;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["projects-summary"] });
      setEditProject(null);
    },
    onError: (e) => setFormError(errMessage(e)),
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/projects/${id}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["projects-summary"] });
    },
  });

  const archiveMutation = useMutation({
    mutationFn: async (p: Project) => {
      const next = p.status === "archived" ? "draft" : "archived";
      await api.patch(`/projects/${p.id}`, { status: next });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["projects-summary"] });
    },
  });

  const summary = summaryQuery.data;
  const recent = recentQuery.data?.items || [];

  return (
    <Stack spacing={3}>
      <PageHeader
        title={`Welcome${user?.display_name ? `, ${user.display_name}` : ""}`}
        subtitle="Create educational videos from slides and AI narration."
        crumbs={[{ label: "Dashboard" }]}
        actions={
          <>
            <Button variant="outlined" component={RouterLink} to="/projects">
              All projects
            </Button>
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
              New project
            </Button>
          </>
        }
      />

      {(summaryQuery.isLoading || recentQuery.isLoading) && (
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress />
        </Box>
      )}

      {summary && (
        <Box
          display="grid"
          gap={2}
          gridTemplateColumns={{ xs: "1fr", sm: "1fr 1fr", lg: "1fr 1fr 1fr 1fr" }}
        >
          <StatCard
            label="Active projects"
            value={summary.draft_projects}
            icon={<FolderOpenIcon />}
            color="#4f46e5"
          />
          <StatCard
            label="Total slides"
            value={summary.total_slides}
            icon={<CollectionsIcon />}
            color="#0ea5e9"
          />
          <StatCard
            label="Voices ready"
            value={summary.ready_audio}
            icon={<RecordVoiceOverIcon />}
            color="#10b981"
          />
          <StatCard
            label="Completed videos"
            value={summary.completed_renders}
            icon={<MovieCreationIcon />}
            color="#f59e0b"
          />
        </Box>
      )}

      <Box display="grid" gap={2} gridTemplateColumns={{ xs: "1fr", md: "1fr 1fr" }}>
        <Card sx={{ border: "1px solid", borderColor: "divider" }}>
          <CardContent>
            <Stack spacing={2}>
              <Box>
                <Typography variant="h6">Quick start</Typography>
                <Typography color="text.secondary" variant="body2">
                  1. Create a project · 2. Upload slides · 3. Add narration · 4. Generate voice · 5. Export MP4
                </Typography>
              </Box>
              <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)} sx={{ alignSelf: "flex-start" }}>
                Start a project
              </Button>
            </Stack>
          </CardContent>
        </Card>
        <Card sx={{ border: "1px solid", borderColor: "divider" }}>
          <CardContent>
            <Stack spacing={2}>
              <Box>
                <Typography variant="h6">Video → slides clipper</Typography>
                <Typography color="text.secondary" variant="body2">
                  Upload a video, extract image clips, write voiceover scripts, then generate AI narration and export.
                </Typography>
              </Box>
              <Button variant="outlined" component={RouterLink} to="/clipper" sx={{ alignSelf: "flex-start" }}>
                Open Video Clipper
              </Button>
            </Stack>
          </CardContent>
        </Card>
      </Box>

      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h5">Recent projects</Typography>
        <Button component={RouterLink} to="/projects" endIcon={<ArrowForwardIcon />}>
          View all
        </Button>
      </Stack>

      {!recentQuery.isLoading && recent.length === 0 && (
        <Card sx={{ border: "1px solid", borderColor: "divider" }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              No projects yet
            </Typography>
            <Typography color="text.secondary" sx={{ mb: 2 }}>
              Create your first learning video project to get started.
            </Typography>
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
              Create project
            </Button>
          </CardContent>
        </Card>
      )}

      <Box
        display="grid"
        gap={2}
        gridTemplateColumns={{ xs: "1fr", sm: "1fr 1fr", lg: "1fr 1fr 1fr" }}
      >
        {recent.map((p) => (
          <ProjectCard
            key={p.id}
            project={p}
            onEdit={(proj) => {
              setFormError("");
              setEditProject(proj);
            }}
            onDelete={(proj) => {
              if (window.confirm(`Delete project “${proj.title}”? This cannot be undone.`)) {
                deleteMutation.mutate(proj.id);
              }
            }}
            onToggleArchive={(proj) => archiveMutation.mutate(proj)}
          />
        ))}
      </Box>

      {(deleteMutation.isError || archiveMutation.isError) && (
        <Alert severity="error">
          {errMessage(deleteMutation.error || archiveMutation.error)}
        </Alert>
      )}

      <ProjectFormDialog
        open={createOpen}
        mode="create"
        loading={createMutation.isPending}
        error={formError}
        onClose={() => {
          setCreateOpen(false);
          setFormError("");
        }}
        onSubmit={(values) => {
          setFormError("");
          createMutation.mutate(values);
        }}
      />

      <ProjectFormDialog
        open={!!editProject}
        mode="edit"
        project={editProject}
        loading={updateMutation.isPending}
        error={formError}
        onClose={() => {
          setEditProject(null);
          setFormError("");
        }}
        onSubmit={(values) => {
          if (!editProject) return;
          setFormError("");
          updateMutation.mutate({ id: editProject.id, values });
        }}
      />
    </Stack>
  );
}
