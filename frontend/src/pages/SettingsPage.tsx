import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { motion } from "framer-motion";
import { api, errMessage } from "../api/client";
import { useAuth, type User } from "../auth/AuthContext";
import PageHeader from "../components/PageHeader";
import { brandColors } from "../theme";

export default function SettingsPage() {
  const { user, setUser } = useAuth();
  const [displayName, setDisplayName] = useState(user?.display_name || "");
  const [email, setEmail] = useState(user?.email || "");
  const [profileError, setProfileError] = useState("");
  const [profileSuccess, setProfileSuccess] = useState("");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState("");

  useEffect(() => {
    setDisplayName(user?.display_name || "");
    setEmail(user?.email || "");
  }, [user?.id, user?.display_name, user?.email]);

  const profileDirty =
    displayName.trim() !== (user?.display_name || "").trim() ||
    email.trim().toLowerCase() !== (user?.email || "").toLowerCase();

  const updateProfile = useMutation({
    mutationFn: async () => {
      const payload: { display_name?: string; email?: string } = {};
      const nextName = displayName.trim();
      const nextEmail = email.trim().toLowerCase();
      if (!nextName) throw new Error("Display name cannot be empty");
      if (!nextEmail || !nextEmail.includes("@")) throw new Error("Enter a valid email");
      if (nextName !== (user?.display_name || "").trim()) payload.display_name = nextName;
      if (nextEmail !== (user?.email || "").toLowerCase()) payload.email = nextEmail;
      if (!Object.keys(payload).length) throw new Error("No changes to save");
      const { data } = await api.patch("/auth/me", payload);
      return data as User;
    },
    onSuccess: (updated) => {
      setUser(updated);
      setProfileSuccess("Profile updated");
      setProfileError("");
    },
    onError: (e) => {
      setProfileSuccess("");
      setProfileError(errMessage(e));
    },
  });

  const changePassword = useMutation({
    mutationFn: async () => {
      await api.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
    },
    onSuccess: () => {
      setPasswordSuccess("Password updated");
      setCurrentPassword("");
      setNewPassword("");
      setConfirm("");
      setPasswordError("");
    },
    onError: (e) => {
      setPasswordSuccess("");
      setPasswordError(errMessage(e));
    },
  });

  const initials = (user?.display_name || user?.email || "?")
    .split(/[\s@]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Settings"
        subtitle="Manage your Naratto account preferences."
        crumbs={[{ label: "Dashboard", to: "/dashboard" }, { label: "Settings" }]}
      />

      <Card
        component={motion.div}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        sx={{ border: "1px solid", borderColor: "divider", maxWidth: 560 }}
      >
        <CardContent>
          <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2.5 }}>
            <Avatar
              sx={{
                width: 56,
                height: 56,
                fontWeight: 800,
                background: `linear-gradient(135deg, ${brandColors.violet}, ${brandColors.cyan})`,
              }}
            >
              {initials}
            </Avatar>
            <Box>
              <Typography variant="h6" fontWeight={800}>
                Profile
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Update your name and email
              </Typography>
            </Box>
          </Stack>
          <Stack spacing={2}>
            {profileError && (
              <Alert severity="error" onClose={() => setProfileError("")}>
                {profileError}
              </Alert>
            )}
            {profileSuccess && (
              <Alert severity="success" onClose={() => setProfileSuccess("")}>
                {profileSuccess}
              </Alert>
            )}
            <TextField
              label="Display name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              fullWidth
              required
              inputProps={{ maxLength: 120 }}
              helperText="Shown in the app header and dashboard"
            />
            <TextField
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              fullWidth
              required
              helperText="Used to sign in"
            />
            <Button
              variant="contained"
              disabled={updateProfile.isPending || !profileDirty || !displayName.trim() || !email.trim()}
              onClick={() => updateProfile.mutate()}
              sx={{ alignSelf: "flex-start" }}
            >
              {updateProfile.isPending ? "Saving…" : "Save profile"}
            </Button>
          </Stack>
        </CardContent>
      </Card>

      <Card
        component={motion.div}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        sx={{ border: "1px solid", borderColor: "divider", maxWidth: 560 }}
      >
        <CardContent>
          <Typography variant="h6" fontWeight={800} gutterBottom>
            Change password
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Use a strong password with at least 8 characters.
          </Typography>
          <Stack spacing={2}>
            {passwordError && (
              <Alert severity="error" onClose={() => setPasswordError("")}>
                {passwordError}
              </Alert>
            )}
            {passwordSuccess && (
              <Alert severity="success" onClose={() => setPasswordSuccess("")}>
                {passwordSuccess}
              </Alert>
            )}
            <TextField
              type="password"
              label="Current password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              fullWidth
              autoComplete="current-password"
            />
            <TextField
              type="password"
              label="New password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              fullWidth
              helperText="At least 8 characters"
              autoComplete="new-password"
            />
            <TextField
              type="password"
              label="Confirm new password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              fullWidth
              autoComplete="new-password"
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
                  setPasswordError("Passwords do not match");
                  return;
                }
                changePassword.mutate();
              }}
              sx={{ alignSelf: "flex-start" }}
            >
              {changePassword.isPending ? "Updating…" : "Update password"}
            </Button>
          </Stack>
        </CardContent>
      </Card>

      <ModelCard />
    </Stack>
  );
}

function ModelCard() {
  const modelsQuery = useQuery({
    queryKey: ["story-models"],
    refetchOnMount: "always",
    queryFn: async () =>
      (await api.get("/models")).data as {
        source: string;
        default_model: string;
        key_configured: boolean;
        gemini_key_configured?: boolean;
        openai_key_configured?: boolean;
        local_available?: boolean;
        local_base_url?: string;
        models: { id: string; name: string; provider?: string }[];
      },
  });
  const catalog = modelsQuery.data;
  const models = catalog?.models ?? [];
  const openai = models.filter((model) => model.provider === "openai");
  const gemini = models.filter((model) => model.provider === "gemini");
  const local = models.filter((model) => model.provider === "local");
  const openRouter = models.filter(
    (model) => model.provider !== "gemini" && model.provider !== "openai" && model.provider !== "local"
  );

  return (
    <Card sx={{ border: "1px solid", borderColor: "divider", maxWidth: 560 }}>
      <CardContent>
        <Typography variant="h6" fontWeight={800} gutterBottom>
          Story models
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Story generation uses a local model, OpenAI, Gemini, or a free OpenRouter text model. The default is{" "}
          {catalog?.default_model || "openrouter/free"}.
        </Typography>
        {catalog && !catalog.openai_key_configured && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            OPENAI_API_KEY is not set. OpenAI models stay in the list.
          </Alert>
        )}
        {catalog && !catalog.gemini_key_configured && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            GEMINI_API_KEY is not set. Gemini models stay in the list.
          </Alert>
        )}
        {catalog && !catalog.key_configured && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            OPENROUTER_API_KEY is not set. Listing models still works.
          </Alert>
        )}
        {catalog && !catalog.local_available && (
          <Alert severity="info" sx={{ mb: 2 }}>
            No local model server is running at {catalog.local_base_url || "http://127.0.0.1:11434/v1"}. Start Ollama
            or LM Studio to generate stories on this machine.
          </Alert>
        )}
        <Typography variant="subtitle2" sx={{ mt: 1 }}>
          Local
        </Typography>
        <Stack spacing={0.5} sx={{ mb: 1.5 }}>
          {local.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              None loaded
            </Typography>
          )}
          {local.map((model) => (
            <Typography key={model.id} variant="body2">
              {model.name}
            </Typography>
          ))}
        </Stack>
        <Typography variant="subtitle2" sx={{ mt: 1 }}>
          OpenAI
        </Typography>
        <Stack spacing={0.5} sx={{ mb: 1.5 }}>
          {openai.map((model) => (
            <Typography key={model.id} variant="body2">
              {model.name}
            </Typography>
          ))}
        </Stack>
        <Typography variant="subtitle2">Gemini</Typography>
        <Stack spacing={0.5} sx={{ mb: 1.5 }}>
          {gemini.map((model) => (
            <Typography key={model.id} variant="body2">
              {model.name}
            </Typography>
          ))}
        </Stack>
        <Typography variant="subtitle2">OpenRouter</Typography>
        <Stack spacing={0.5}>
          {openRouter.map((model) => (
            <Typography key={model.id} variant="body2">
              {model.name}
            </Typography>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}
