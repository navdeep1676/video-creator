import { useEffect, useState } from "react";
import {
  Alert,
  Button,
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
} from "@mui/material";
import type { Project } from "../types/project";

export type ProjectFormValues = {
  title: string;
  description: string;
  status?: string;
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

  useEffect(() => {
    if (open) {
      setTitle(project?.title || "");
      setDescription(project?.description || "");
      setStatus(project?.status || "draft");
    }
  }, [open, project]);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{mode === "create" ? "New project" : "Edit project"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            label="Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            fullWidth
            autoFocus
            required
            inputProps={{ maxLength: 200 }}
          />
          <TextField
            label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            fullWidth
            multiline
            minRows={3}
            placeholder="Optional notes about this learning video…"
          />
          {mode === "edit" && (
            <FormControl fullWidth>
              <InputLabel>Status</InputLabel>
              <Select label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
                <MenuItem value="draft">Draft (active)</MenuItem>
                <MenuItem value="archived">Archived</MenuItem>
              </Select>
            </FormControl>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={loading}>
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
            })
          }
        >
          {loading ? "Saving…" : mode === "create" ? "Create project" : "Save changes"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
