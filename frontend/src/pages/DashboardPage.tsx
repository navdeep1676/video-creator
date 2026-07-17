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
import ContentCutIcon from "@mui/icons-material/ContentCut";
import RocketLaunchIcon from "@mui/icons-material/RocketLaunch";
import { motion } from "framer-motion";
import { api, errMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import PageHeader from "../components/PageHeader";
import ProjectCard from "../components/ProjectCard";
import ProjectFormDialog, { type ProjectFormValues } from "../components/ProjectFormDialog";
import ConfirmDialog from "../components/ConfirmDialog";
import type { Project, ProjectListResponse, ProjectSummary } from "../types/project";
import { brandColors } from "../theme";

function StatCard({
  label,
  value,
  icon,
  gradient,
  delay = 0,
}: {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  gradient: string;
  delay?: number;
}) {
  return (
    <Card
      component={motion.div}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -3 }}
      sx={{
        height: "100%",
        overflow: "hidden",
        position: "relative",
        "&:hover": {
          boxShadow: "0 14px 36px rgba(109, 40, 217, 0.12)",
          borderColor: "rgba(109, 40, 217, 0.18)",
        },
      }}
    >
      <CardContent sx={{ position: "relative", zIndex: 1 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
          <Box>
            <Typography variant="body2" color="text.secondary" fontWeight={600} gutterBottom>
              {label}
            </Typography>
            <Typography variant="h4" fontWeight={800} letterSpacing="-0.03em">
              {value}
            </Typography>
          </Box>
          <Box
            sx={{
              width: 46,
              height: 46,
              borderRadius: 2.5,
              display: "grid",
              placeItems: "center",
              background: gradient,
              color: "#fff",
              boxShadow: "0 8px 18px rgba(15, 23, 42, 0.15)",
            }}
          >
            {icon}
          </Box>
        </Stack>
      </CardContent>
      <Box
        sx={{
          position: "absolute",
          right: -20,
          bottom: -24,
          width: 90,
          height: 90,
          borderRadius: "50%",
          background: gradient,
          opacity: 0.08,
        }}
      />
    </Card>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [createOpen, setCreateOpen] = useState(false);
  const [editProject, setEditProject] = useState<Project | null>(null);
  const [deleteProject, setDeleteProject] = useState<Project | null>(null);
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
        aspect_ratio: values.aspect_ratio || "16:9",
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
        aspect_ratio: values.aspect_ratio,
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
      setDeleteProject(null);
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
        subtitle="Create educational videos from slides and AI narration with Naratto."
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
            gradient={`linear-gradient(135deg, ${brandColors.violet}, ${brandColors.indigo})`}
            delay={0}
          />
          <StatCard
            label="Total slides"
            value={summary.total_slides}
            icon={<CollectionsIcon />}
            gradient={`linear-gradient(135deg, ${brandColors.cyan}, #0EA5E9)`}
            delay={0.05}
          />
          <StatCard
            label="Voices ready"
            value={summary.ready_audio}
            icon={<RecordVoiceOverIcon />}
            gradient="linear-gradient(135deg, #10B981, #059669)"
            delay={0.1}
          />
          <StatCard
            label="Completed videos"
            value={summary.completed_renders}
            icon={<MovieCreationIcon />}
            gradient="linear-gradient(135deg, #F59E0B, #F43F5E)"
            delay={0.15}
          />
        </Box>
      )}

      <Box display="grid" gap={2} gridTemplateColumns={{ xs: "1fr", md: "1fr 1fr" }}>
        <Card
          component={motion.div}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          whileHover={{ y: -2 }}
          sx={{
            border: "1px solid",
            borderColor: "divider",
            background: `linear-gradient(135deg, rgba(109,40,217,0.06) 0%, rgba(255,255,255,0.95) 55%)`,
          }}
        >
          <CardContent>
            <Stack spacing={2}>
              <Box
                sx={{
                  width: 42,
                  height: 42,
                  borderRadius: 2,
                  display: "grid",
                  placeItems: "center",
                  background: `linear-gradient(135deg, ${brandColors.violet}, ${brandColors.indigo})`,
                  color: "#fff",
                }}
              >
                <RocketLaunchIcon fontSize="small" />
              </Box>
              <Box>
                <Typography variant="h6" fontWeight={800}>
                  Quick start
                </Typography>
                <Typography color="text.secondary" variant="body2" sx={{ mt: 0.5 }}>
                  1. Create a project · 2. Upload slides · 3. Add narration · 4. Generate voice · 5. Export MP4
                </Typography>
              </Box>
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={() => setCreateOpen(true)}
                sx={{ alignSelf: "flex-start" }}
              >
                Start a project
              </Button>
            </Stack>
          </CardContent>
        </Card>
        <Card
          component={motion.div}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          whileHover={{ y: -2 }}
          sx={{
            border: "1px solid",
            borderColor: "divider",
            background: `linear-gradient(135deg, rgba(6,182,212,0.07) 0%, rgba(255,255,255,0.95) 55%)`,
          }}
        >
          <CardContent>
            <Stack spacing={2}>
              <Box
                sx={{
                  width: 42,
                  height: 42,
                  borderRadius: 2,
                  display: "grid",
                  placeItems: "center",
                  background: `linear-gradient(135deg, ${brandColors.cyan}, #0EA5E9)`,
                  color: "#fff",
                }}
              >
                <ContentCutIcon fontSize="small" />
              </Box>
              <Box>
                <Typography variant="h6" fontWeight={800}>
                  Video → slides clipper
                </Typography>
                <Typography color="text.secondary" variant="body2" sx={{ mt: 0.5 }}>
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
        <Typography variant="h5" fontWeight={800}>
          Recent projects
        </Typography>
        <Button component={RouterLink} to="/projects" endIcon={<ArrowForwardIcon />}>
          View all
        </Button>
      </Stack>

      {!recentQuery.isLoading && recent.length === 0 && (
        <Card sx={{ border: "1px solid", borderColor: "divider" }}>
          <CardContent>
            <Typography variant="h6" fontWeight={800} gutterBottom>
              No projects yet
            </Typography>
            <Typography color="text.secondary" sx={{ mb: 2 }}>
              Create your first Naratto project to get started.
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
        {recent.map((p, i) => (
          <Box
            key={p.id}
            component={motion.div}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 * i, duration: 0.3 }}
          >
            <ProjectCard
              project={p}
              onEdit={(proj) => {
                setFormError("");
                setEditProject(proj);
              }}
              onDelete={(proj) => setDeleteProject(proj)}
              onToggleArchive={(proj) => archiveMutation.mutate(proj)}
            />
          </Box>
        ))}
      </Box>

      {(deleteMutation.isError || archiveMutation.isError) && (
        <Alert severity="error">{errMessage(deleteMutation.error || archiveMutation.error)}</Alert>
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

      <ConfirmDialog
        open={!!deleteProject}
        title="Delete project?"
        description="This permanently removes the project, all slides, narration audio, and exported videos. This cannot be undone."
        highlight={deleteProject?.title}
        confirmLabel="Delete project"
        loading={deleteMutation.isPending}
        tone="danger"
        onClose={() => {
          if (!deleteMutation.isPending) setDeleteProject(null);
        }}
        onConfirm={() => {
          if (deleteProject) deleteMutation.mutate(deleteProject.id);
        }}
      />
    </Stack>
  );
}
