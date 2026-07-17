import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import MovieCreationOutlinedIcon from "@mui/icons-material/MovieCreationOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import type { Project } from "../types/project";
import {
  ASPECT_RATIO_OPTIONS,
  DEFAULT_ASPECT_RATIO,
  type AspectRatioId,
  type AspectRatioOption,
  getAspectOption,
} from "../types/aspectRatio";
import { brandColors } from "../theme";

export type ProjectFormValues = {
  title: string;
  description: string;
  status?: string;
  aspect_ratio?: AspectRatioId;
};

type Props = {
  open: boolean;
  mode: "create" | "edit";
  project?: Project | null;
  loading?: boolean;
  error?: string;
  onClose: () => void;
  onSubmit: (values: ProjectFormValues) => void;
};

const CATEGORY_LABEL: Record<string, string> = {
  long: "Long-form",
  short: "Shorts",
  square: "Feed",
  social: "Social",
};

function FormatPreview({
  option,
  selected,
}: {
  option: AspectRatioOption;
  selected: boolean;
}) {
  // Fixed stage so every card lines up; frame scales inside it
  const stage = 48;
  const scale = stage / Math.max(option.width, option.height);
  const w = Math.max(14, Math.round(option.width * scale));
  const h = Math.max(14, Math.round(option.height * scale));

  return (
    <Box
      sx={{
        height: 64,
        borderRadius: 1.5,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        bgcolor: selected ? "rgba(109,40,217,0.08)" : "rgba(15,23,42,0.04)",
        border: "1px solid",
        borderColor: selected ? "rgba(109,40,217,0.18)" : "divider",
        mb: 1,
        position: "relative",
        overflow: "hidden",
        transition: "background-color 0.18s ease, border-color 0.18s ease",
      }}
    >
      <Box
        sx={{
          position: "absolute",
          inset: 0,
          opacity: 0.3,
          backgroundImage:
            "linear-gradient(rgba(100,116,139,0.12) 1px, transparent 1px), linear-gradient(90deg, rgba(100,116,139,0.12) 1px, transparent 1px)",
          backgroundSize: "10px 10px",
          pointerEvents: "none",
        }}
      />
      <Box
        sx={{
          width: w,
          height: h,
          borderRadius: option.id === "9:16" || option.id === "4:5" ? 1 : 0.75,
          position: "relative",
          zIndex: 1,
          background: selected
            ? `linear-gradient(160deg, ${brandColors.violetLight} 0%, ${brandColors.violet} 45%, ${brandColors.indigo} 100%)`
            : "linear-gradient(160deg, #E2E8F0 0%, #CBD5E1 55%, #94A3B8 100%)",
          boxShadow: selected
            ? `0 6px 14px ${brandColors.violet}38, inset 0 1px 0 rgba(255,255,255,0.25)`
            : "0 4px 10px rgba(15,23,42,0.1), inset 0 1px 0 rgba(255,255,255,0.35)",
          transition: "transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease",
          transform: selected ? "scale(1.03)" : "scale(1)",
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "center",
          pb: 0.5,
        }}
      >
        <Box
          sx={{
            width: "55%",
            height: 2,
            borderRadius: 1,
            bgcolor: "rgba(255,255,255,0.55)",
          }}
        />
      </Box>
    </Box>
  );
}

function FormatCard({
  option,
  selected,
  disabled,
  onSelect,
}: {
  option: AspectRatioOption;
  selected: boolean;
  disabled?: boolean;
  onSelect: () => void;
}) {
  return (
    <Box
      component="button"
      type="button"
      disabled={disabled}
      onClick={onSelect}
      aria-pressed={selected}
      sx={{
        all: "unset",
        boxSizing: "border-box",
        cursor: disabled ? "not-allowed" : "pointer",
        display: "block",
        width: "100%",
        height: "100%",
        borderRadius: 2,
        border: "1.5px solid",
        borderColor: selected ? "primary.main" : "divider",
        bgcolor: selected ? "rgba(109,40,217,0.03)" : "background.paper",
        p: 1.15,
        opacity: disabled && !selected ? 0.5 : 1,
        transition: "border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease, background 0.15s ease",
        boxShadow: selected ? `0 6px 16px ${brandColors.violet}18` : "0 1px 2px rgba(15,23,42,0.04)",
        transform: selected ? "translateY(-1px)" : "none",
        position: "relative",
        "&:hover": disabled
          ? {}
          : {
              borderColor: selected ? "primary.main" : "rgba(109,40,217,0.35)",
              boxShadow: selected
                ? `0 8px 18px ${brandColors.violet}22`
                : "0 4px 12px rgba(15,23,42,0.07)",
            },
        "&:focus-visible": {
          outline: `2px solid ${brandColors.violet}`,
          outlineOffset: 2,
        },
      }}
    >
      {selected && (
        <CheckCircleRoundedIcon
          sx={{
            position: "absolute",
            top: 8,
            right: 8,
            fontSize: 18,
            color: "primary.main",
            zIndex: 2,
            bgcolor: "#fff",
            borderRadius: "50%",
          }}
        />
      )}

      <FormatPreview option={option} selected={selected} />

      <Stack spacing={0.5}>
        <Typography
          variant="body2"
          fontWeight={800}
          sx={{ lineHeight: 1.25, pr: selected ? 2 : 0, fontSize: 13 }}
        >
          {option.label}
        </Typography>

        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap alignItems="center">
          <Chip
            size="small"
            label={option.id}
            sx={{
              height: 20,
              fontWeight: 700,
              fontSize: 10,
              bgcolor: selected ? "rgba(109,40,217,0.12)" : "action.hover",
              color: selected ? "primary.main" : "text.secondary",
            }}
          />
          <Chip
            size="small"
            label={CATEGORY_LABEL[option.category] || option.category}
            variant="outlined"
            sx={{ height: 20, fontSize: 10, fontWeight: 600 }}
          />
        </Stack>

        <Typography
          variant="caption"
          color="text.secondary"
          sx={{
            lineHeight: 1.35,
            fontSize: 11,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {option.width}×{option.height}
          <Box component="span" sx={{ mx: 0.4, opacity: 0.5 }}>
            ·
          </Box>
          {option.description}
        </Typography>
      </Stack>
    </Box>
  );
}

export default function ProjectFormDialog({
  open,
  mode,
  project,
  loading,
  error,
  onClose,
  onSubmit,
}: Props) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("draft");
  const [aspectRatio, setAspectRatio] = useState<AspectRatioId>(DEFAULT_ASPECT_RATIO);

  const hasSlides = (project?.slide_count ?? 0) > 0;
  const lockedRatio = mode === "edit" && hasSlides;
  const isCreate = mode === "create";

  useEffect(() => {
    if (open) {
      setTitle(project?.title || "");
      setDescription(project?.description || "");
      setStatus(project?.status || "draft");
      setAspectRatio((project?.aspect_ratio as AspectRatioId) || DEFAULT_ASPECT_RATIO);
    }
  }, [open, project]);

  const selected = getAspectOption(aspectRatio);

  return (
    <Dialog
      open={open}
      onClose={loading ? undefined : onClose}
      fullWidth
      maxWidth="md"
      transitionDuration={220}
      PaperProps={{
        sx: {
          borderRadius: 3,
          border: "1px solid",
          borderColor: "divider",
          overflow: "hidden",
          maxHeight: "92vh",
        },
      }}
    >
      {/* Header band */}
      <Box
        sx={{
          px: { xs: 2.5, sm: 4 },
          pt: { xs: 2.75, sm: 3.25 },
          pb: { xs: 2.25, sm: 2.75 },
          background: isCreate
            ? `linear-gradient(135deg, rgba(109,40,217,0.08) 0%, rgba(6,182,212,0.06) 100%)`
            : `linear-gradient(135deg, rgba(15,23,42,0.04) 0%, rgba(109,40,217,0.06) 100%)`,
          borderBottom: "1px solid",
          borderColor: "divider",
        }}
      >
        <Stack direction="row" spacing={1.75} alignItems="center">
          <Box
            sx={{
              width: 44,
              height: 44,
              borderRadius: 2,
              display: "grid",
              placeItems: "center",
              background: `linear-gradient(135deg, ${brandColors.violet}, ${brandColors.indigo})`,
              color: "#fff",
              boxShadow: `0 8px 18px ${brandColors.violet}33`,
            }}
          >
            {isCreate ? <MovieCreationOutlinedIcon fontSize="small" /> : <EditOutlinedIcon fontSize="small" />}
          </Box>
          <Box>
            <Typography variant="h6" fontWeight={800} sx={{ lineHeight: 1.25 }}>
              {isCreate ? "Create project" : "Edit project"}
            </Typography>
            <Typography variant="body2" color="text.secondary" fontWeight={500}>
              {isCreate
                ? "Name it, pick a video format, then add slides and narration."
                : "Update title, description, format, or status."}
            </Typography>
          </Box>
        </Stack>
      </Box>

      <DialogTitle sx={{ display: "none" }}>{isCreate ? "Create project" : "Edit project"}</DialogTitle>

      <DialogContent
        dividers={false}
        sx={{
          // MUI collapses top padding on DialogContent; force consistent inset
          px: { xs: 2.5, sm: 4 },
          pt: { xs: "20px !important", sm: "28px !important" },
          pb: { xs: 2.5, sm: 3 },
        }}
      >
        <Stack spacing={3}>
          {error && (
            <Alert severity="error" sx={{ borderRadius: 2 }}>
              {error}
            </Alert>
          )}

          <TextField
            label="Project title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            fullWidth
            autoFocus
            required
            placeholder="e.g. Intro to photosynthesis"
            inputProps={{ maxLength: 200 }}
            helperText={`${title.trim().length}/200`}
          />

          <TextField
            label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            fullWidth
            multiline
            minRows={2}
            maxRows={5}
            placeholder="Optional notes for this learning video…"
          />

          <Box>
            <Stack direction="row" alignItems="baseline" justifyContent="space-between" gap={1} sx={{ mb: 0.5 }}>
              <Typography variant="subtitle1" fontWeight={800}>
                Video format
              </Typography>
              {!isCreate && lockedRatio && (
                <Chip size="small" label="Locked" color="warning" variant="outlined" sx={{ height: 22 }} />
              )}
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.75 }}>
              {isCreate
                ? "Choose the export frame. Uploads are scaled to fit with padding (nothing is cropped)."
                : lockedRatio
                  ? "Format is locked because this project already has slides. Create a new project for another ratio."
                  : "You can change the format only while the project has no slides."}
            </Typography>

            <Box
              role="radiogroup"
              aria-label="Video format"
              sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
                gap: 1.15,
              }}
            >
              {ASPECT_RATIO_OPTIONS.map((r) => (
                <FormatCard
                  key={r.id}
                  option={r}
                  selected={aspectRatio === r.id}
                  disabled={lockedRatio}
                  onSelect={() => setAspectRatio(r.id)}
                />
              ))}
            </Box>

            <Box
              sx={{
                mt: 1.75,
                px: 1.75,
                py: 1.25,
                borderRadius: 2,
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 1,
                bgcolor: "rgba(109,40,217,0.05)",
                border: "1px solid",
                borderColor: "rgba(109,40,217,0.12)",
              }}
            >
              <Chip
                size="small"
                color="primary"
                label={selected.id}
                sx={{ fontWeight: 700, height: 24 }}
              />
              <Typography variant="body2" color="text.secondary">
                <Box component="strong" sx={{ color: "text.primary", fontWeight: 700 }}>
                  {selected.label}
                </Box>
                {" · "}
                canvas {selected.width}×{selected.height}
                {" · "}
                images scale to fit (no crop)
              </Typography>
            </Box>
          </Box>

          {mode === "edit" && (
            <FormControl fullWidth>
              <InputLabel id="project-status-label">Status</InputLabel>
              <Select
                labelId="project-status-label"
                label="Status"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <MenuItem value="draft">Draft (active)</MenuItem>
                <MenuItem value="archived">Archived</MenuItem>
              </Select>
            </FormControl>
          )}
        </Stack>
      </DialogContent>

      <DialogActions
        sx={{
          px: { xs: 2.5, sm: 4 },
          py: { xs: 2, sm: 2.5 },
          gap: 1.25,
          borderTop: "1px solid",
          borderColor: "divider",
          bgcolor: "rgba(248,250,252,0.8)",
        }}
      >
        <Button onClick={onClose} disabled={loading} color="inherit" sx={{ borderRadius: 2 }}>
          Cancel
        </Button>
        <Button
          variant="contained"
          disabled={!title.trim() || loading}
          onClick={() =>
            onSubmit({
              title: title.trim(),
              description: description.trim(),
              status: mode === "edit" ? status : undefined,
              aspect_ratio: aspectRatio,
            })
          }
          sx={{ borderRadius: 2, minWidth: 140, px: 2.5 }}
        >
          {loading ? "Saving…" : isCreate ? "Create project" : "Save changes"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
