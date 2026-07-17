import { Navigate, Route, Routes } from "react-router-dom";
import { Box, CircularProgress } from "@mui/material";
import { useAuth } from "./auth/AuthContext";
import AppLayout from "./components/AppLayout";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import DashboardPage from "./pages/DashboardPage";
import ProjectsPage from "./pages/ProjectsPage";
import ProjectPage from "./pages/ProjectPage";
import ExportPage from "./pages/ExportPage";
import SettingsPage from "./pages/SettingsPage";
import ClipperPage from "./pages/ClipperPage";

function LoadingScreen() {
  return (
    <Box
      minHeight="100vh"
      display="flex"
      flexDirection="column"
      alignItems="center"
      justifyContent="center"
      gap={2}
      sx={{
        background:
          "radial-gradient(ellipse 70% 50% at 50% 30%, rgba(109,40,217,0.12), transparent)," +
          "linear-gradient(180deg, #F8F7FF 0%, #F1F5F9 100%)",
      }}
    >
      <CircularProgress size={36} thickness={4} />
      <Box component="span" sx={{ fontWeight: 800, letterSpacing: "-0.03em", color: "text.secondary", fontSize: 14 }}>
        Loading Naratto…
      </Box>
    </Box>
  );
}

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <LoadingScreen />;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function GuestOnly({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <LoadingScreen />;
  if (user) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route
        path="/login"
        element={
          <GuestOnly>
            <LoginPage />
          </GuestOnly>
        }
      />
      <Route
        path="/register"
        element={
          <GuestOnly>
            <RegisterPage />
          </GuestOnly>
        }
      />
      <Route
        element={
          <Protected>
            <AppLayout />
          </Protected>
        }
      >
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:projectId" element={<ProjectPage />} />
        <Route path="projects/:projectId/export" element={<ExportPage />} />
        <Route path="clipper" element={<ClipperPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
