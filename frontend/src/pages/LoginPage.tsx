import { useState } from "react";
import { Link as RouterLink, Navigate, useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Link,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { motion } from "framer-motion";
import { useAuth } from "../auth/AuthContext";
import { errMessage } from "../api/client";
import BrandLogo from "../components/BrandLogo";
import { brandColors } from "../theme";

export default function LoginPage() {
  const { user, login, loading } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (!loading && user) return <Navigate to="/dashboard" replace />;

  return (
    <Box
      minHeight="100vh"
      display="grid"
      gridTemplateColumns={{ xs: "1fr", md: "1.05fr 0.95fr" }}
      sx={{ overflow: "hidden" }}
    >
      <Box
        sx={{
          display: { xs: "none", md: "flex" },
          flexDirection: "column",
          justifyContent: "space-between",
          p: 6,
          position: "relative",
          background: `linear-gradient(160deg, ${brandColors.sidebar} 0%, #151B2E 45%, #1E1B4B 100%)`,
          color: "#F8FAFC",
          overflow: "hidden",
          "&::before": {
            content: '""',
            position: "absolute",
            width: 420,
            height: 420,
            borderRadius: "50%",
            top: -100,
            right: -80,
            background: "radial-gradient(circle, rgba(109,40,217,0.45), transparent 70%)",
          },
          "&::after": {
            content: '""',
            position: "absolute",
            width: 320,
            height: 320,
            borderRadius: "50%",
            bottom: -60,
            left: -40,
            background: "radial-gradient(circle, rgba(6,182,212,0.25), transparent 70%)",
          },
        }}
      >
        <BrandLogo inverted size="lg" subtitle="Learning video studio" />
        <Box sx={{ position: "relative", zIndex: 1, maxWidth: 440 }}>
          <Typography
            variant="h3"
            sx={{ fontWeight: 800, letterSpacing: "-0.03em", mb: 2, lineHeight: 1.15 }}
          >
            Narrate once.
            <br />
            Teach forever.
          </Typography>
          <Typography sx={{ color: "rgba(226,232,240,0.75)", fontSize: 17, lineHeight: 1.65 }}>
            Naratto turns slides and scripts into polished educational videos with AI voice, motion,
            and export-ready MP4s.
          </Typography>
          <Stack direction="row" spacing={1.5} sx={{ mt: 4 }}>
            {["AI voice", "Ken Burns", "Subtitles", "FFmpeg export"].map((t) => (
              <Box
                key={t}
                sx={{
                  px: 1.5,
                  py: 0.75,
                  borderRadius: 999,
                  border: "1px solid rgba(255,255,255,0.12)",
                  bgcolor: "rgba(255,255,255,0.06)",
                  fontSize: 12,
                  fontWeight: 700,
                  color: "rgba(248,250,252,0.9)",
                }}
              >
                {t}
              </Box>
            ))}
          </Stack>
        </Box>
        <Typography variant="caption" sx={{ color: "rgba(148,163,184,0.7)", position: "relative", zIndex: 1 }}>
          © {new Date().getFullYear()} Naratto
        </Typography>
      </Box>

      <Box
        display="flex"
        alignItems="center"
        justifyContent="center"
        p={{ xs: 2.5, sm: 4 }}
        sx={{
          background:
            "radial-gradient(ellipse 70% 50% at 50% 0%, rgba(109,40,217,0.1), transparent)," +
            "linear-gradient(180deg, #F8F7FF 0%, #F1F5F9 100%)",
        }}
      >
        <Card
          component={motion.div}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          sx={{ width: 440, maxWidth: "100%", border: "1px solid", borderColor: "divider" }}
        >
          <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
            <Stack spacing={2.5}>
              <Box sx={{ display: { xs: "block", md: "none" }, mb: 0.5 }}>
                <BrandLogo size="md" subtitle="Learning video studio" />
              </Box>
              <Box>
                <Typography variant="h5" fontWeight={800} letterSpacing="-0.02em">
                  Welcome back
                </Typography>
                <Typography color="text.secondary" variant="body2" sx={{ mt: 0.75 }}>
                  Sign in to create learning videos from slides and narration.
                </Typography>
              </Box>
              {error && <Alert severity="error">{error}</Alert>}
              <TextField
                label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                fullWidth
                autoComplete="email"
              />
              <TextField
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                fullWidth
                autoComplete="current-password"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    (document.getElementById("naratto-login-btn") as HTMLButtonElement | null)?.click();
                  }
                }}
              />
              <Button
                id="naratto-login-btn"
                variant="contained"
                size="large"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  setError("");
                  try {
                    await login(email, password);
                    navigate("/dashboard");
                  } catch (e) {
                    setError(errMessage(e));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {busy ? "Signing in…" : "Sign in"}
              </Button>
              <Typography variant="body2" color="text.secondary">
                No account?{" "}
                <Link component={RouterLink} to="/register" fontWeight={700}>
                  Create one
                </Link>
              </Typography>
            </Stack>
          </CardContent>
        </Card>
      </Box>
    </Box>
  );
}
