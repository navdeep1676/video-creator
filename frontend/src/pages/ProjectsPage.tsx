import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  FormControl,
  InputAdornment,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";
import { api, errMessage } from "../api/client";
import PageHeader from "../components/PageHeader";
import ProjectCard from "../components/ProjectCard";
import ProjectFormDialog, { type ProjectFormValues } from "../components/ProjectFormDialog";
import type { Project, ProjectListResponse } from "../types/project";

export default function ProjectsPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [editProject, setEditProject] = useState<Project | null>(null);
  const [formError, setFormError] = useState("");
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  const projectsQuery = useQuery({
    queryKey: ["projects", status, debouncedSearch],
    queryFn: async () => {
      const { data } = await api.get("/projects", {
        params: {
          status,
          limit: 100,
          q: debouncedSearch || undefined,
        },
      });
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
      setActionError("");
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
    onError: (e) => setActionError(errMessage(e)),
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
    onError: (e) => setActionError(errMessage(e)),
  });

  const items = projectsQuery.data?.items || [];
  const total = projectsQuery.data?.total ?? 0;

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Projects"
        subtitle="Create, edit, archive, and manage all learning video projects."
        crumbs={[{ label: "Dashboard", to: "/" }, { label: "Projects" }]}
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
            New project
          </Button>
        }
      />

      <Card sx={{ border: "1px solid", borderColor: "divider" }}>
        <CardContent>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              fullWidth
              placeholder="Search projects…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon color="action" />
                  </InputAdornment>
                ),
              }}
            />
            <FormControl sx={{ minWidth: 180 }}>
              <InputLabel>Status</InputLabel>
              <Select label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
                <MenuItem value="all">All</MenuItem>
                <MenuItem value="draft">Draft</MenuItem>
                <MenuItem value="archived">Archived</MenuItem>
              </Select>
            </FormControl>
          </Stack>
        </CardContent>
      </Card>

      {actionError && (
        <Alert severity="error" onClose={() => setActionError("")}>
          {actionError}
        </Alert>
      )}

      {projectsQuery.isLoading && (
        <Box display="flex" justifyContent="center" py={6}>
          <CircularProgress />
        </Box>
      )}

      {projectsQuery.isError && (
        <Alert severity="error">{errMessage(projectsQuery.error)}</Alert>
      )}

      {!projectsQuery.isLoading && items.length === 0 && (
        <Card sx={{ border: "1px solid", borderColor: "divider" }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              No projects found
            </Typography>
            <Typography color="text.secondary" sx={{ mb: 2 }}>
              {debouncedSearch || status !== "all"
                ? "Try changing filters or create a new project."
                : "Create your first project to start building learning videos."}
            </Typography>
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
              New project
            </Button>
          </CardContent>
        </Card>
      )}

      {!projectsQuery.isLoading && items.length > 0 && (
        <>
          <Typography variant="body2" color="text.secondary">
            Showing {items.length} of {total} project{total === 1 ? "" : "s"}
          </Typography>
          <Box
            display="grid"
            gap={2}
            gridTemplateColumns={{ xs: "1fr", sm: "1fr 1fr", lg: "1fr 1fr 1fr" }}
          >
            {items.map((p) => (
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
        </>
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
