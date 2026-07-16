import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  CardContent,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { api, errMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import PageHeader from "../components/PageHeader";

export default function SettingsPage() {
  const { user } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const changePassword = useMutation({
    mutationFn: async () => {
      await api.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
    },
    onSuccess: () => {
      setSuccess("Password updated");
      setCurrentPassword("");
      setNewPassword("");
      setConfirm("");
      setError("");
    },
    onError: (e) => {
      setSuccess("");
      setError(errMessage(e));
    },
  });

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Settings"
        subtitle="Manage your account preferences."
        crumbs={[{ label: "Dashboard", to: "/" }, { label: "Settings" }]}
      />

      <Card sx={{ border: "1px solid", borderColor: "divider", maxWidth: 560 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Profile
          </Typography>
          <Stack spacing={1.5}>
            <TextField label="Display name" value={user?.display_name || ""} fullWidth disabled />
            <TextField label="Email" value={user?.email || ""} fullWidth disabled />
          </Stack>
        </CardContent>
      </Card>

      <Card sx={{ border: "1px solid", borderColor: "divider", maxWidth: 560 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Change password
          </Typography>
          <Stack spacing={2}>
            {error && <Alert severity="error">{error}</Alert>}
            {success && <Alert severity="success">{success}</Alert>}
            <TextField
              type="password"
              label="Current password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              fullWidth
            />
            <TextField
              type="password"
              label="New password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              fullWidth
              helperText="At least 8 characters"
            />
            <TextField
              type="password"
              label="Confirm new password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              fullWidth
            />
            <Button
              variant="contained"
              disabled={
                changePassword.isPending ||
                !currentPassword ||
                newPassword.length < 8 ||
                newPassword !== confirm
              }
              onClick={() => {
                if (newPassword !== confirm) {
                  setError("Passwords do not match");
                  return;
                }
                changePassword.mutate();
              }}
            >
              Update password
            </Button>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
