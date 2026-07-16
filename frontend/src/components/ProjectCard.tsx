import {
  Box,
  Card,
  CardActions,
  CardContent,
  Chip,
  IconButton,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ArchiveOutlinedIcon from "@mui/icons-material/ArchiveOutlined";
import UnarchiveOutlinedIcon from "@mui/icons-material/UnarchiveOutlined";
import MovieCreationIcon from "@mui/icons-material/MovieCreation";
import CollectionsIcon from "@mui/icons-material/Collections";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";
import { Link as RouterLink } from "react-router-dom";
import type { Project } from "../types/project";

function formatBytes(n: number): string {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function statusColor(status?: string | null): "default" | "success" | "warning" | "error" | "info" {
  switch (status) {
    case "completed":
      return "success";
    case "processing":
    case "queued":
      return "info";
    case "failed":
      return "error";
    case "archived":
      return "default";
    default:
      return "warning";
  }
}

type Props = {
  project: Project;
  onEdit: (p: Project) => void;
  onDelete: (p: Project) => void;
  onToggleArchive: (p: Project) => void;
};

export default function ProjectCard({ project, onEdit, onDelete, onToggleArchive }: Props) {
  const slides = project.slide_count ?? 0;
  const ready = project.ready_audio_count ?? 0;
  const voicePct = slides > 0 ? Math.round((ready / slides) * 100) : 0;

  return (
    <Card
      sx={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        opacity: project.status === "archived" ? 0.85 : 1,
        border: "1px solid",
        borderColor: "divider",
      }}
    >
      <CardContent
        component={RouterLink}
        to={`/projects/${project.id}`}
        sx={{ flex: 1, textDecoration: "none", color: "inherit", "&:hover": { bgcolor: "action.hover" } }}
      >
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
          <Typography variant="h6" sx={{ lineHeight: 1.3 }}>
            {project.title}
          </Typography>
          <Chip
            size="small"
            label={project.status}
            color={project.status === "archived" ? "default" : "primary"}
            variant={project.status === "archived" ? "outlined" : "filled"}
          />
        </Stack>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{
            mt: 1,
            mb: 2,
            minHeight: 40,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {project.description || "No description"}
        </Typography>

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
          <Chip size="small" icon={<CollectionsIcon />} label={`${slides} slides`} variant="outlined" />
          <Chip size="small" icon={<RecordVoiceOverIcon />} label={`${ready} voices`} variant="outlined" />
          <Chip
            size="small"
            icon={<MovieCreationIcon />}
            label={
              project.last_render_status
                ? `Render: ${project.last_render_status}`
                : "No render yet"
            }
            color={statusColor(project.last_render_status)}
            variant="outlined"
          />
        </Stack>

        <Box>
          <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              Voice readiness
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {voicePct}%
            </Typography>
          </Stack>
          <LinearProgress
            variant="determinate"
            value={voicePct}
            sx={{ height: 6, borderRadius: 3 }}
          />
        </Box>

        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 2 }}>
          Updated {new Date(project.updated_at).toLocaleString()} · {formatBytes(project.storage_bytes || 0)}
        </Typography>
      </CardContent>

      <CardActions sx={{ px: 1.5, pb: 1.5, justifyContent: "flex-end" }}>
        <Tooltip title="Edit">
          <IconButton size="small" onClick={() => onEdit(project)} aria-label="Edit project">
            <EditOutlinedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title={project.status === "archived" ? "Restore to draft" : "Archive"}>
          <IconButton
            size="small"
            onClick={() => onToggleArchive(project)}
            aria-label="Archive project"
          >
            {project.status === "archived" ? (
              <UnarchiveOutlinedIcon fontSize="small" />
            ) : (
              <ArchiveOutlinedIcon fontSize="small" />
            )}
          </IconButton>
        </Tooltip>
        <Tooltip title="Delete">
          <IconButton size="small" color="error" onClick={() => onDelete(project)} aria-label="Delete project">
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </CardActions>
    </Card>
  );
}
