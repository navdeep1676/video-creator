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
import { useAuth } from "../auth/AuthContext";
import { errMessage } from "../api/client";

export default function LoginPage() {
  const { user, login, loading } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (!loading && user) return <Navigate to="/" replace />;

  return (
    <Box minHeight="100vh" display="flex" alignItems="center" justifyContent="center" p={2}>
      <Card sx={{ width: 420, maxWidth: "100%" }}>
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h5">Welcome back</Typography>
            <Typography color="text.secondary" variant="body2">
              Sign in to create learning videos from slides and narration.
            </Typography>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} fullWidth />
            <TextField
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              fullWidth
            />
            <Button
              variant="contained"
              size="large"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError("");
                try {
                  await login(email, password);
                  navigate("/");
                } catch (e) {
                  setError(errMessage(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              Sign in
            </Button>
            <Typography variant="body2">
              No account? <Link component={RouterLink} to="/register">Create one</Link>
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
