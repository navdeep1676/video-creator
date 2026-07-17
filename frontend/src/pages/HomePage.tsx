import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import {
  Box,
  Button,
  Card,
  CardContent,
  Container,
  Divider,
  Drawer,
  IconButton,
  Stack,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import MenuIcon from "@mui/icons-material/Menu";
import CloseIcon from "@mui/icons-material/Close";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import CollectionsIcon from "@mui/icons-material/Collections";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";
import MovieCreationIcon from "@mui/icons-material/MovieCreation";
import ContentCutIcon from "@mui/icons-material/ContentCut";
import SubtitlesIcon from "@mui/icons-material/Subtitles";
import SpeedIcon from "@mui/icons-material/Speed";
import PlayArrowRoundedIcon from "@mui/icons-material/PlayArrowRounded";
import SchoolOutlinedIcon from "@mui/icons-material/SchoolOutlined";
import BusinessCenterOutlinedIcon from "@mui/icons-material/BusinessCenterOutlined";
import CreateOutlinedIcon from "@mui/icons-material/CreateOutlined";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import BoltRoundedIcon from "@mui/icons-material/BoltRounded";
import { motion } from "framer-motion";
import BrandLogo from "../components/BrandLogo";
import { useAuth } from "../auth/AuthContext";
import { brandColors } from "../theme";

const navLinks = [
  { href: "#features", label: "Features" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#use-cases", label: "Use cases" },
  { href: "#pipeline", label: "Pipeline" },
];

const features = [
  {
    icon: <CollectionsIcon />,
    title: "Slide-first projects",
    body: "Upload multi-image slides, drag to reorder, and lock aspect ratios for clean, consistent exports.",
    gradient: `linear-gradient(135deg, ${brandColors.violet}, ${brandColors.indigo})`,
  },
  {
    icon: <RecordVoiceOverIcon />,
    title: "AI narration",
    body: "Write per-slide scripts, pick a voice, and generate natural speech asynchronously—preview before render.",
    gradient: `linear-gradient(135deg, ${brandColors.cyan}, #0EA5E9)`,
  },
  {
    icon: <MovieCreationIcon />,
    title: "Polished motion",
    body: "Ken Burns zooms, smooth transitions, and timeline assembly so lessons feel like pro e-learning.",
    gradient: "linear-gradient(135deg, #F59E0B, #F43F5E)",
  },
  {
    icon: <SubtitlesIcon />,
    title: "Subtitles & music",
    body: "Burn-in captions and optional BGM so every export is classroom- and LMS-ready.",
    gradient: "linear-gradient(135deg, #10B981, #059669)",
  },
  {
    icon: <ContentCutIcon />,
    title: "Video clipper",
    body: "Extract stills from existing footage, turn them into slides, then narrate and export.",
    gradient: `linear-gradient(135deg, ${brandColors.violetLight}, ${brandColors.cyan})`,
  },
  {
    icon: <SpeedIcon />,
    title: "Background renders",
    body: "FFmpeg workers queue heavy jobs so you keep editing while MP4s finish in the background.",
    gradient: "linear-gradient(135deg, #6366F1, #8B5CF6)",
  },
];

const steps = [
  {
    n: "01",
    title: "Create a project",
    body: "Name it, choose 16:9, 9:16, or another format that matches your platform.",
    icon: <CreateOutlinedIcon />,
  },
  {
    n: "02",
    title: "Upload slides",
    body: "Drop PNG/JPG images, reorder the flow, and keep visuals locked to the canvas.",
    icon: <CollectionsIcon />,
  },
  {
    n: "03",
    title: "Write & voice",
    body: "Add narration, choose a voice, generate AI speech, and fine-tune timing.",
    icon: <RecordVoiceOverIcon />,
  },
  {
    n: "04",
    title: "Export MP4",
    body: "Render with motion and subtitles, then download a polished learning video.",
    icon: <MovieCreationIcon />,
  },
];

const useCases = [
  {
    icon: <SchoolOutlinedIcon />,
    title: "Educators",
    body: "Turn lecture slides into bingeable lessons students can rewatch anytime.",
    points: ["Consistent voiceovers", "Caption-ready exports", "Classroom formats"],
  },
  {
    icon: <BusinessCenterOutlinedIcon />,
    title: "L&D teams",
    body: "Ship training modules faster without a full video production crew.",
    points: ["Brand-ready motion", "Repeatable pipeline", "Async renders"],
  },
  {
    icon: <CreateOutlinedIcon />,
    title: "Creators",
    body: "Repurpose decks and clips into short-form or long-form educational content.",
    points: ["Clipper workflow", "Vertical + landscape", "AI voice drafts"],
  },
];

const stats = [
  { value: "4", label: "Steps to export" },
  { value: "AI", label: "Native voiceover" },
  { value: "MP4", label: "Studio-ready" },
  { value: "24/7", label: "Background jobs" },
];

const pipeline = [
  { title: "Slides", desc: "Images in order" },
  { title: "Script", desc: "Per-slide narration" },
  { title: "Voice", desc: "AI TTS audio" },
  { title: "Motion", desc: "Ken Burns + fades" },
  { title: "Export", desc: "Subtitles + MP4" },
];

const fadeUp = {
  hidden: { opacity: 0, y: 22 },
  show: (i = 0) => ({
    opacity: 1,
    y: 0,
    transition: { delay: 0.05 * i, duration: 0.45, ease: [0.22, 1, 0.36, 1] },
  }),
};

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <Typography
      variant="overline"
      sx={{
        color: brandColors.violet,
        fontWeight: 800,
        letterSpacing: "0.14em",
        display: "inline-flex",
        alignItems: "center",
        gap: 1,
        WebkitTextFillColor: brandColors.violet,
      }}
    >
      <Box
        sx={{
          width: 18,
          height: 2,
          borderRadius: 1,
          background: `linear-gradient(90deg, ${brandColors.violet}, ${brandColors.cyan})`,
        }}
      />
      {children}
    </Typography>
  );
}

function WhiteCtaButton({
  to,
  children,
  endIcon,
}: {
  to: string;
  children: React.ReactNode;
  endIcon?: React.ReactNode;
}) {
  return (
    <Button
      component={RouterLink}
      to={to}
      variant="contained"
      size="large"
      endIcon={endIcon}
      sx={{
        backgroundColor: "#ffffff",
        backgroundImage: "none",
        color: brandColors.violet,
        WebkitTextFillColor: brandColors.violet,
        px: 3,
        boxShadow: "0 10px 28px rgba(0,0,0,0.22)",
        "&:hover": {
          backgroundColor: "#F8FAFC",
          backgroundImage: "none",
          color: brandColors.violetDark,
          WebkitTextFillColor: brandColors.violetDark,
        },
        "& .MuiButton-endIcon, & .MuiSvgIcon-root": { color: "inherit" },
      }}
    >
      {children}
    </Button>
  );
}

export default function HomePage() {
  const { user, loading } = useAuth();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const [menuOpen, setMenuOpen] = useState(false);

  const primaryCta = user ? "/dashboard" : "/register";
  const primaryLabel = user ? "Open studio" : "Get started free";
  const secondaryCta = user ? "/projects" : "/login";
  const secondaryLabel = user ? "My projects" : "Sign in";

  return (
    <Box sx={{ minHeight: "100vh", overflow: "hidden", bgcolor: "#FAFAFF" }}>
      {/* Nav */}
      <Box
        component="header"
        sx={{
          position: "sticky",
          top: 0,
          zIndex: 30,
          borderBottom: "1px solid",
          borderColor: "rgba(15, 23, 42, 0.06)",
          backdropFilter: "blur(16px) saturate(1.2)",
          bgcolor: "rgba(255, 255, 255, 0.78)",
        }}
      >
        <Container maxWidth="lg">
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ py: 1.25, minHeight: 70 }}>
            <Box component={RouterLink} to="/" sx={{ textDecoration: "none" }}>
              <BrandLogo size="md" subtitle={isMobile ? undefined : "Learning video studio"} />
            </Box>

            {!isMobile && (
              <Stack direction="row" spacing={0.5} alignItems="center">
                {navLinks.map((l) => (
                  <Button
                    key={l.href}
                    href={l.href}
                    color="inherit"
                    sx={{
                      fontWeight: 600,
                      color: "text.secondary",
                      WebkitTextFillColor: "currentColor",
                      px: 1.5,
                      "&:hover": { color: "primary.main", bgcolor: "rgba(109,40,217,0.06)" },
                    }}
                  >
                    {l.label}
                  </Button>
                ))}
              </Stack>
            )}

            <Stack direction="row" spacing={1} alignItems="center">
              {!isMobile && !loading && !user && (
                <Button
                  component={RouterLink}
                  to="/login"
                  color="inherit"
                  sx={{ fontWeight: 700, WebkitTextFillColor: "currentColor" }}
                >
                  Sign in
                </Button>
              )}
              {!isMobile && (
                <Button
                  component={RouterLink}
                  to={primaryCta}
                  variant="contained"
                  endIcon={<ArrowForwardIcon />}
                >
                  {user ? "Dashboard" : "Start free"}
                </Button>
              )}
              {isMobile && (
                <IconButton onClick={() => setMenuOpen(true)} aria-label="Open menu">
                  <MenuIcon />
                </IconButton>
              )}
            </Stack>
          </Stack>
        </Container>
      </Box>

      <Drawer
        anchor="right"
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        PaperProps={{
          sx: {
            width: 300,
            p: 2.5,
            background: `linear-gradient(180deg, ${brandColors.sidebar} 0%, #12182B 100%)`,
            color: "#F8FAFC",
          },
        }}
      >
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
          <BrandLogo inverted size="sm" />
          <IconButton onClick={() => setMenuOpen(false)} sx={{ color: "#fff" }} aria-label="Close menu">
            <CloseIcon />
          </IconButton>
        </Stack>
        <Stack spacing={0.5}>
          {navLinks.map((l) => (
            <Button
              key={l.href}
              href={l.href}
              onClick={() => setMenuOpen(false)}
              sx={{
                justifyContent: "flex-start",
                color: "rgba(248,250,252,0.9)",
                WebkitTextFillColor: "rgba(248,250,252,0.9)",
                fontWeight: 700,
                py: 1.25,
              }}
            >
              {l.label}
            </Button>
          ))}
        </Stack>
        <Divider sx={{ borderColor: "rgba(255,255,255,0.1)", my: 2.5 }} />
        <Stack spacing={1.25}>
          {!user && (
            <Button
              component={RouterLink}
              to="/login"
              onClick={() => setMenuOpen(false)}
              variant="outlined"
              fullWidth
              sx={{
                color: "#fff",
                WebkitTextFillColor: "#fff",
                borderColor: "rgba(255,255,255,0.35)",
              }}
            >
              Sign in
            </Button>
          )}
          <Button
            component={RouterLink}
            to={primaryCta}
            onClick={() => setMenuOpen(false)}
            variant="contained"
            fullWidth
            endIcon={<ArrowForwardIcon />}
          >
            {user ? "Dashboard" : "Start free"}
          </Button>
        </Stack>
      </Drawer>

      {/* Hero */}
      <Box
        component="section"
        sx={{
          position: "relative",
          pt: { xs: 5, md: 9 },
          pb: { xs: 7, md: 10 },
          overflow: "hidden",
        }}
      >
        {/* Ambient blobs */}
        <Box
          sx={{
            position: "absolute",
            inset: 0,
            pointerEvents: "none",
            background:
              "radial-gradient(ellipse 70% 55% at 15% 10%, rgba(109,40,217,0.18), transparent 55%)," +
              "radial-gradient(ellipse 55% 45% at 90% 15%, rgba(6,182,212,0.14), transparent 50%)," +
              "radial-gradient(ellipse 40% 30% at 60% 80%, rgba(244,63,94,0.06), transparent 50%)," +
              "linear-gradient(180deg, #F7F5FF 0%, #F1F5F9 55%, #FAFAFF 100%)",
          }}
        />
        <Box
          component={motion.div}
          animate={{ y: [0, -12, 0], opacity: [0.4, 0.7, 0.4] }}
          transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
          sx={{
            position: "absolute",
            width: 280,
            height: 280,
            borderRadius: "50%",
            top: 80,
            right: "8%",
            background: "radial-gradient(circle, rgba(139,92,246,0.35), transparent 70%)",
            filter: "blur(20px)",
            pointerEvents: "none",
          }}
        />

        <Container maxWidth="lg" sx={{ position: "relative", zIndex: 1 }}>
          <Box
            display="grid"
            gap={{ xs: 5, md: 7 }}
            gridTemplateColumns={{ xs: "1fr", md: "1.05fr 0.95fr" }}
            alignItems="center"
          >
            <Box
              component={motion.div}
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
            >
              <Box
                sx={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 1,
                  px: 1.75,
                  py: 0.85,
                  mb: 2.75,
                  borderRadius: 999,
                  border: "1px solid",
                  borderColor: "rgba(109, 40, 217, 0.22)",
                  bgcolor: "rgba(255,255,255,0.75)",
                  boxShadow: "0 8px 24px rgba(109,40,217,0.08)",
                }}
              >
                <BoltRoundedIcon sx={{ fontSize: 16, color: brandColors.violet }} />
                <Typography
                  variant="caption"
                  fontWeight={800}
                  sx={{ color: brandColors.violet, WebkitTextFillColor: brandColors.violet }}
                >
                  Slides + AI voice → polished MP4
                </Typography>
              </Box>

              <Typography
                variant="h2"
                component="h1"
                sx={{
                  fontWeight: 800,
                  letterSpacing: "-0.04em",
                  lineHeight: 1.05,
                  fontSize: { xs: "2.5rem", sm: "3.15rem", md: "3.65rem" },
                  mb: 2.25,
                  color: brandColors.ink,
                  WebkitTextFillColor: brandColors.ink,
                }}
              >
                Narrate once.
                <Box
                  component="span"
                  sx={{
                    display: "block",
                    background: `linear-gradient(120deg, ${brandColors.indigo} 0%, ${brandColors.violet} 45%, ${brandColors.cyan} 100%)`,
                    backgroundClip: "text",
                    WebkitBackgroundClip: "text",
                    color: "transparent",
                    WebkitTextFillColor: "transparent",
                  }}
                >
                  Teach forever.
                </Box>
              </Typography>

              <Typography
                sx={{
                  fontSize: { xs: 16.5, md: 18.5 },
                  lineHeight: 1.7,
                  maxWidth: 520,
                  mb: 3.5,
                  color: brandColors.slate,
                  WebkitTextFillColor: brandColors.slate,
                }}
              >
                Naratto is the learning video studio that turns decks and scripts into export-ready
                educational videos—with AI narration, motion, subtitles, and background FFmpeg
                renders.
              </Typography>

              <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mb: 3 }}>
                <Button
                  component={RouterLink}
                  to={primaryCta}
                  variant="contained"
                  size="large"
                  endIcon={<ArrowForwardIcon />}
                  sx={{ px: 3, py: 1.35 }}
                >
                  {primaryLabel}
                </Button>
                <Button
                  component={RouterLink}
                  to={secondaryCta}
                  variant="outlined"
                  size="large"
                  startIcon={
                    !user ? (
                      <PlayArrowRoundedIcon sx={{ fontSize: 22 }} />
                    ) : undefined
                  }
                  sx={{ px: 3, py: 1.35, bgcolor: "rgba(255,255,255,0.8)" }}
                >
                  {secondaryLabel}
                </Button>
              </Stack>

              <Stack direction="row" spacing={2.5} flexWrap="wrap" useFlexGap alignItems="center">
                {["No video editor needed", "AI voice built-in", "MP4 in minutes"].map((t) => (
                  <Stack key={t} direction="row" spacing={0.75} alignItems="center">
                    <CheckCircleRoundedIcon sx={{ fontSize: 18, color: "#10B981" }} />
                    <Typography
                      variant="body2"
                      fontWeight={700}
                      sx={{ color: brandColors.ink, WebkitTextFillColor: brandColors.ink }}
                    >
                      {t}
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            </Box>

            {/* Hero product mock */}
            <Box
              component={motion.div}
              initial={{ opacity: 0, scale: 0.94, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.12, ease: [0.22, 1, 0.36, 1] }}
              sx={{ position: "relative" }}
            >
              {/* Floating badge */}
              <Box
                component={motion.div}
                animate={{ y: [0, -8, 0] }}
                transition={{ duration: 4.5, repeat: Infinity, ease: "easeInOut" }}
                sx={{
                  position: "absolute",
                  top: { xs: -8, md: 12 },
                  left: { xs: 8, md: -16 },
                  zIndex: 3,
                  px: 1.75,
                  py: 1.1,
                  borderRadius: 3,
                  bgcolor: "#fff",
                  border: "1px solid",
                  borderColor: "rgba(15,23,42,0.06)",
                  boxShadow: "0 14px 36px rgba(15,23,42,0.1)",
                  display: "flex",
                  alignItems: "center",
                  gap: 1,
                }}
              >
                <Box
                  sx={{
                    width: 32,
                    height: 32,
                    borderRadius: 2,
                    display: "grid",
                    placeItems: "center",
                    background: `linear-gradient(135deg, ${brandColors.violet}, ${brandColors.cyan})`,
                    color: "#fff",
                  }}
                >
                  <AutoAwesomeIcon sx={{ fontSize: 18 }} />
                </Box>
                <Box>
                  <Typography variant="caption" fontWeight={800} display="block" lineHeight={1.2}>
                    Voice ready
                  </Typography>
                  <Typography variant="caption" color="text.secondary" fontWeight={600}>
                    3 of 4 slides
                  </Typography>
                </Box>
              </Box>

              <Card
                sx={{
                  borderRadius: 4.5,
                  overflow: "hidden",
                  border: "1px solid",
                  borderColor: "rgba(109, 40, 217, 0.14)",
                  boxShadow: "0 40px 80px rgba(79, 70, 229, 0.2)",
                  background: `linear-gradient(165deg, ${brandColors.sidebar} 0%, #12182B 42%, #1E1B4B 100%)`,
                  color: "#F8FAFC",
                }}
              >
                <Box
                  sx={{
                    px: 2.25,
                    py: 1.5,
                    borderBottom: "1px solid rgba(255,255,255,0.08)",
                    display: "flex",
                    alignItems: "center",
                    gap: 1,
                  }}
                >
                  {["#F43F5E", "#F59E0B", "#10B981"].map((c) => (
                    <Box key={c} sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: c }} />
                  ))}
                  <Typography
                    variant="caption"
                    sx={{
                      ml: 1,
                      color: "rgba(226,232,240,0.65)",
                      WebkitTextFillColor: "rgba(226,232,240,0.65)",
                      fontWeight: 700,
                    }}
                  >
                    project · Photosynthesis 101
                  </Typography>
                  <Box sx={{ flex: 1 }} />
                  <Box
                    sx={{
                      px: 1.25,
                      py: 0.35,
                      borderRadius: 999,
                      bgcolor: "rgba(16,185,129,0.15)",
                      border: "1px solid rgba(16,185,129,0.35)",
                      fontSize: 11,
                      fontWeight: 800,
                      color: "#6EE7B7",
                      WebkitTextFillColor: "#6EE7B7",
                    }}
                  >
                    Rendering
                  </Box>
                </Box>

                <CardContent sx={{ p: { xs: 2.25, sm: 3 } }}>
                  {/* Fake video stage */}
                  <Box
                    sx={{
                      position: "relative",
                      borderRadius: 3,
                      overflow: "hidden",
                      mb: 2.25,
                      aspectRatio: "16 / 9",
                      background:
                        "linear-gradient(145deg, rgba(109,40,217,0.35) 0%, rgba(15,23,42,0.9) 40%, rgba(6,182,212,0.25) 100%)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      display: "grid",
                      placeItems: "center",
                    }}
                  >
                    <Box
                      sx={{
                        position: "absolute",
                        inset: 0,
                        background:
                          "radial-gradient(circle at 30% 30%, rgba(255,255,255,0.12), transparent 45%)",
                      }}
                    />
                    <Box
                      component={motion.div}
                      animate={{ scale: [1, 1.06, 1] }}
                      transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut" }}
                      sx={{
                        width: 64,
                        height: 64,
                        borderRadius: "50%",
                        bgcolor: "rgba(255,255,255,0.14)",
                        border: "1px solid rgba(255,255,255,0.25)",
                        display: "grid",
                        placeItems: "center",
                        backdropFilter: "blur(8px)",
                      }}
                    >
                      <PlayArrowRoundedIcon sx={{ fontSize: 36, color: "#fff" }} />
                    </Box>
                    <Typography
                      variant="caption"
                      sx={{
                        position: "absolute",
                        left: 14,
                        bottom: 12,
                        fontWeight: 700,
                        color: "rgba(248,250,252,0.85)",
                        WebkitTextFillColor: "rgba(248,250,252,0.85)",
                        bgcolor: "rgba(0,0,0,0.35)",
                        px: 1,
                        py: 0.35,
                        borderRadius: 1,
                      }}
                    >
                      00:42 / 02:18
                    </Typography>
                  </Box>

                  <Stack spacing={1.25}>
                    {[
                      { label: "Slide 1 · Intro", status: "Voice ready", ok: true, pct: 100 },
                      { label: "Slide 2 · Light reaction", status: "Generating…", ok: false, pct: 62 },
                      { label: "Slide 3 · Summary", status: "Script draft", ok: false, pct: 20 },
                    ].map((row, i) => (
                      <Box
                        key={row.label}
                        component={motion.div}
                        initial={{ opacity: 0, x: 14 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.28 + i * 0.09 }}
                        sx={{
                          display: "flex",
                          alignItems: "center",
                          gap: 1.5,
                          p: 1.35,
                          borderRadius: 2.5,
                          bgcolor: "rgba(255,255,255,0.045)",
                          border: "1px solid rgba(255,255,255,0.08)",
                        }}
                      >
                        <Box
                          sx={{
                            width: 46,
                            height: 34,
                            borderRadius: 1.25,
                            flexShrink: 0,
                            background:
                              i === 0
                                ? `linear-gradient(135deg, ${brandColors.violet}, ${brandColors.cyan})`
                                : i === 1
                                  ? "linear-gradient(135deg, #6366F1, #A78BFA)"
                                  : "linear-gradient(135deg, #0EA5E9, #22D3EE)",
                          }}
                        />
                        <Box flex={1} minWidth={0}>
                          <Typography
                            variant="body2"
                            fontWeight={700}
                            noWrap
                            sx={{ color: "#F8FAFC", WebkitTextFillColor: "#F8FAFC" }}
                          >
                            {row.label}
                          </Typography>
                          <Box
                            sx={{
                              mt: 0.65,
                              height: 4,
                              borderRadius: 2,
                              bgcolor: "rgba(255,255,255,0.08)",
                              overflow: "hidden",
                            }}
                          >
                            <Box
                              component={motion.div}
                              initial={{ width: 0 }}
                              animate={{ width: `${row.pct}%` }}
                              transition={{ delay: 0.4 + i * 0.1, duration: 0.9 }}
                              sx={{
                                height: "100%",
                                borderRadius: 2,
                                background: row.ok
                                  ? "linear-gradient(90deg, #10B981, #34D399)"
                                  : `linear-gradient(90deg, ${brandColors.violet}, ${brandColors.cyan})`,
                              }}
                            />
                          </Box>
                        </Box>
                        <Typography
                          variant="caption"
                          fontWeight={700}
                          sx={{
                            color: row.ok ? "#6EE7B7" : "rgba(226,232,240,0.65)",
                            WebkitTextFillColor: row.ok ? "#6EE7B7" : "rgba(226,232,240,0.65)",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {row.status}
                        </Typography>
                      </Box>
                    ))}
                  </Stack>
                </CardContent>
              </Card>

              {/* Floating export chip */}
              <Box
                component={motion.div}
                animate={{ y: [0, 8, 0] }}
                transition={{ duration: 5, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
                sx={{
                  position: "absolute",
                  bottom: { xs: -12, md: 28 },
                  right: { xs: 8, md: -18 },
                  zIndex: 3,
                  px: 1.75,
                  py: 1.15,
                  borderRadius: 3,
                  bgcolor: "#fff",
                  border: "1px solid",
                  borderColor: "rgba(15,23,42,0.06)",
                  boxShadow: "0 14px 36px rgba(15,23,42,0.12)",
                }}
              >
                <Typography variant="caption" fontWeight={800} display="block" color="text.primary">
                  Export · 1080p MP4
                </Typography>
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  Subtitles + Ken Burns
                </Typography>
              </Box>
            </Box>
          </Box>

          {/* Stats strip */}
          <Box
            component={motion.div}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35, duration: 0.45 }}
            sx={{
              mt: { xs: 7, md: 9 },
              display: "grid",
              gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4, 1fr)" },
              gap: 2,
            }}
          >
            {stats.map((s) => (
              <Box
                key={s.label}
                sx={{
                  p: 2.25,
                  borderRadius: 3,
                  bgcolor: "rgba(255,255,255,0.72)",
                  border: "1px solid",
                  borderColor: "rgba(15,23,42,0.06)",
                  textAlign: "center",
                  backdropFilter: "blur(8px)",
                }}
              >
                <Typography
                  sx={{
                    fontWeight: 800,
                    fontSize: { xs: 26, md: 30 },
                    letterSpacing: "-0.03em",
                    color: brandColors.violet,
                    WebkitTextFillColor: brandColors.violet,
                    lineHeight: 1.1,
                  }}
                >
                  {s.value}
                </Typography>
                <Typography
                  variant="body2"
                  fontWeight={600}
                  sx={{ mt: 0.5, color: brandColors.slate, WebkitTextFillColor: brandColors.slate }}
                >
                  {s.label}
                </Typography>
              </Box>
            ))}
          </Box>
        </Container>
      </Box>

      {/* Features */}
      <Box id="features" component="section" sx={{ py: { xs: 8, md: 11 }, bgcolor: "#fff" }}>
        <Container maxWidth="lg">
          <Box sx={{ textAlign: "center", mb: 6, maxWidth: 600, mx: "auto" }}>
            <SectionLabel>Features</SectionLabel>
            <Typography
              variant="h3"
              sx={{
                fontWeight: 800,
                letterSpacing: "-0.03em",
                mt: 1.25,
                mb: 1.5,
                fontSize: { xs: "1.85rem", md: "2.35rem" },
                color: brandColors.ink,
                WebkitTextFillColor: brandColors.ink,
              }}
            >
              Everything to ship a lesson video
            </Typography>
            <Typography sx={{ color: brandColors.slate, WebkitTextFillColor: brandColors.slate, fontSize: 16.5 }}>
              From first slide to final MP4—built for educators, trainers, and content teams who want
              speed without sacrificing polish.
            </Typography>
          </Box>

          <Box
            display="grid"
            gap={2.5}
            gridTemplateColumns={{ xs: "1fr", sm: "1fr 1fr", lg: "1fr 1fr 1fr" }}
          >
            {features.map((f, i) => (
              <Card
                key={f.title}
                component={motion.div}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true, margin: "-50px" }}
                whileHover={{ y: -6 }}
                sx={{
                  height: "100%",
                  border: "1px solid",
                  borderColor: "divider",
                  position: "relative",
                  overflow: "hidden",
                  "&:hover": {
                    borderColor: "rgba(109, 40, 217, 0.28)",
                    boxShadow: "0 20px 48px rgba(109, 40, 217, 0.12)",
                  },
                  "&::before": {
                    content: '""',
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    height: 3,
                    background: f.gradient,
                    opacity: 0,
                    transition: "opacity 0.2s ease",
                  },
                  "&:hover::before": { opacity: 1 },
                }}
              >
                <CardContent sx={{ p: 3 }}>
                  <Box
                    sx={{
                      width: 48,
                      height: 48,
                      borderRadius: 2.5,
                      display: "grid",
                      placeItems: "center",
                      background: f.gradient,
                      color: "#fff",
                      mb: 2.25,
                      boxShadow: "0 10px 22px rgba(15,23,42,0.14)",
                    }}
                  >
                    {f.icon}
                  </Box>
                  <Typography
                    variant="h6"
                    fontWeight={800}
                    gutterBottom
                    sx={{ color: brandColors.ink, WebkitTextFillColor: brandColors.ink }}
                  >
                    {f.title}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{ lineHeight: 1.7, color: brandColors.slate, WebkitTextFillColor: brandColors.slate }}
                  >
                    {f.body}
                  </Typography>
                </CardContent>
              </Card>
            ))}
          </Box>
        </Container>
      </Box>

      {/* How it works */}
      <Box
        id="how-it-works"
        component="section"
        sx={{
          py: { xs: 8, md: 11 },
          background:
            "radial-gradient(ellipse 70% 50% at 50% 0%, rgba(109,40,217,0.09), transparent)," +
            "linear-gradient(180deg, #F8F7FF 0%, #EEF2FF 100%)",
        }}
      >
        <Container maxWidth="lg">
          <Box sx={{ textAlign: "center", mb: 6 }}>
            <SectionLabel>How it works</SectionLabel>
            <Typography
              variant="h3"
              sx={{
                fontWeight: 800,
                letterSpacing: "-0.03em",
                mt: 1.25,
                fontSize: { xs: "1.85rem", md: "2.35rem" },
                color: brandColors.ink,
                WebkitTextFillColor: brandColors.ink,
              }}
            >
              Four steps to an MP4
            </Typography>
          </Box>

          <Box
            display="grid"
            gap={2.5}
            gridTemplateColumns={{ xs: "1fr", sm: "1fr 1fr", md: "1fr 1fr 1fr 1fr" }}
            sx={{ position: "relative" }}
          >
            {steps.map((s, i) => (
              <Box
                key={s.n}
                component={motion.div}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true, margin: "-40px" }}
                sx={{
                  p: 3,
                  borderRadius: 3.5,
                  bgcolor: "background.paper",
                  border: "1px solid",
                  borderColor: "divider",
                  height: "100%",
                  position: "relative",
                  boxShadow: "0 8px 28px rgba(15,23,42,0.04)",
                }}
              >
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 2 }}>
                  <Typography
                    sx={{
                      fontWeight: 800,
                      fontSize: 28,
                      letterSpacing: "-0.04em",
                      color: brandColors.violet,
                      WebkitTextFillColor: brandColors.violet,
                      lineHeight: 1,
                    }}
                  >
                    {s.n}
                  </Typography>
                  <Box
                    sx={{
                      width: 40,
                      height: 40,
                      borderRadius: 2,
                      display: "grid",
                      placeItems: "center",
                      bgcolor: "rgba(109,40,217,0.08)",
                      color: brandColors.violet,
                    }}
                  >
                    {s.icon}
                  </Box>
                </Stack>
                <Typography
                  variant="h6"
                  fontWeight={800}
                  gutterBottom
                  sx={{ color: brandColors.ink, WebkitTextFillColor: brandColors.ink }}
                >
                  {s.title}
                </Typography>
                <Typography
                  variant="body2"
                  sx={{ color: brandColors.slate, WebkitTextFillColor: brandColors.slate, lineHeight: 1.65 }}
                >
                  {s.body}
                </Typography>
              </Box>
            ))}
          </Box>
        </Container>
      </Box>

      {/* Use cases */}
      <Box id="use-cases" component="section" sx={{ py: { xs: 8, md: 11 }, bgcolor: "#fff" }}>
        <Container maxWidth="lg">
          <Box sx={{ textAlign: "center", mb: 6, maxWidth: 560, mx: "auto" }}>
            <SectionLabel>Use cases</SectionLabel>
            <Typography
              variant="h3"
              sx={{
                fontWeight: 800,
                letterSpacing: "-0.03em",
                mt: 1.25,
                mb: 1.5,
                fontSize: { xs: "1.85rem", md: "2.35rem" },
                color: brandColors.ink,
                WebkitTextFillColor: brandColors.ink,
              }}
            >
              Built for people who teach
            </Typography>
            <Typography sx={{ color: brandColors.slate, WebkitTextFillColor: brandColors.slate }}>
              Whether you run a classroom, train a team, or publish explainers—Naratto fits the workflow.
            </Typography>
          </Box>

          <Box display="grid" gap={2.5} gridTemplateColumns={{ xs: "1fr", md: "1fr 1fr 1fr" }}>
            {useCases.map((u, i) => (
              <Card
                key={u.title}
                component={motion.div}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true, margin: "-40px" }}
                whileHover={{ y: -4 }}
                sx={{
                  height: "100%",
                  border: "1px solid",
                  borderColor: "divider",
                  background:
                    i === 1
                      ? `linear-gradient(160deg, rgba(109,40,217,0.06) 0%, #fff 50%)`
                      : "linear-gradient(180deg, #fff 0%, #FAFAFF 100%)",
                }}
              >
                <CardContent sx={{ p: 3.25 }}>
                  <Box
                    sx={{
                      width: 48,
                      height: 48,
                      borderRadius: 2.5,
                      mb: 2,
                      display: "grid",
                      placeItems: "center",
                      background: `linear-gradient(135deg, ${brandColors.violet}, ${brandColors.indigo})`,
                      color: "#fff",
                      boxShadow: `0 10px 22px ${brandColors.violet}33`,
                    }}
                  >
                    {u.icon}
                  </Box>
                  <Typography
                    variant="h6"
                    fontWeight={800}
                    gutterBottom
                    sx={{ color: brandColors.ink, WebkitTextFillColor: brandColors.ink }}
                  >
                    {u.title}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      mb: 2,
                      color: brandColors.slate,
                      WebkitTextFillColor: brandColors.slate,
                      lineHeight: 1.65,
                    }}
                  >
                    {u.body}
                  </Typography>
                  <Stack spacing={1}>
                    {u.points.map((p) => (
                      <Stack key={p} direction="row" spacing={1} alignItems="center">
                        <CheckCircleRoundedIcon sx={{ fontSize: 18, color: brandColors.violet }} />
                        <Typography
                          variant="body2"
                          fontWeight={600}
                          sx={{ color: brandColors.ink, WebkitTextFillColor: brandColors.ink }}
                        >
                          {p}
                        </Typography>
                      </Stack>
                    ))}
                  </Stack>
                </CardContent>
              </Card>
            ))}
          </Box>
        </Container>
      </Box>

      {/* Pipeline */}
      <Box
        id="pipeline"
        component="section"
        sx={{
          py: { xs: 8, md: 11 },
          background: `linear-gradient(180deg, #0B1020 0%, #12182B 50%, #1E1B4B 100%)`,
          color: "#F8FAFC",
          position: "relative",
          overflow: "hidden",
        }}
      >
        <Box
          sx={{
            position: "absolute",
            inset: 0,
            pointerEvents: "none",
            background:
              "radial-gradient(ellipse 50% 40% at 20% 30%, rgba(109,40,217,0.35), transparent)," +
              "radial-gradient(ellipse 40% 35% at 80% 70%, rgba(6,182,212,0.2), transparent)",
          }}
        />
        <Container maxWidth="lg" sx={{ position: "relative", zIndex: 1 }}>
          <Box sx={{ textAlign: "center", mb: 5, maxWidth: 560, mx: "auto" }}>
            <Typography
              variant="overline"
              sx={{
                color: brandColors.violetLight,
                WebkitTextFillColor: brandColors.violetLight,
                fontWeight: 800,
                letterSpacing: "0.14em",
              }}
            >
              Pipeline
            </Typography>
            <Typography
              variant="h3"
              sx={{
                fontWeight: 800,
                letterSpacing: "-0.03em",
                mt: 1.25,
                mb: 1.5,
                fontSize: { xs: "1.85rem", md: "2.35rem" },
                color: "#F8FAFC",
                WebkitTextFillColor: "#F8FAFC",
              }}
            >
              One flow from idea to video
            </Typography>
            <Typography sx={{ color: "rgba(226,232,240,0.7)", WebkitTextFillColor: "rgba(226,232,240,0.7)" }}>
              Naratto keeps narration, motion, and export in a single studio timeline.
            </Typography>
          </Box>

          <Box
            display="grid"
            gap={1.5}
            gridTemplateColumns={{ xs: "1fr", sm: "repeat(5, 1fr)" }}
            alignItems="stretch"
          >
            {pipeline.map((p, i) => (
              <Box
                key={p.title}
                component={motion.div}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true }}
                sx={{
                  p: 2.5,
                  borderRadius: 3,
                  border: "1px solid rgba(255,255,255,0.1)",
                  bgcolor: "rgba(255,255,255,0.04)",
                  textAlign: "center",
                  position: "relative",
                }}
              >
                <Typography
                  sx={{
                    fontWeight: 800,
                    fontSize: 12,
                    letterSpacing: "0.08em",
                    color: brandColors.cyan,
                    WebkitTextFillColor: brandColors.cyan,
                    mb: 1,
                  }}
                >
                  STEP {i + 1}
                </Typography>
                <Typography
                  variant="h6"
                  fontWeight={800}
                  sx={{ color: "#F8FAFC", WebkitTextFillColor: "#F8FAFC", mb: 0.5 }}
                >
                  {p.title}
                </Typography>
                <Typography
                  variant="body2"
                  sx={{ color: "rgba(226,232,240,0.65)", WebkitTextFillColor: "rgba(226,232,240,0.65)" }}
                >
                  {p.desc}
                </Typography>
              </Box>
            ))}
          </Box>

          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} justifyContent="center" sx={{ mt: 5 }}>
            <WhiteCtaButton to={primaryCta} endIcon={<ArrowForwardIcon />}>
              {primaryLabel}
            </WhiteCtaButton>
            <Button
              component={RouterLink}
              to={user ? "/clipper" : "/login"}
              size="large"
              variant="outlined"
              sx={{
                color: "#ffffff",
                WebkitTextFillColor: "#ffffff",
                borderColor: "rgba(255,255,255,0.4)",
                "&:hover": {
                  borderColor: "#fff",
                  bgcolor: "rgba(255,255,255,0.08)",
                  color: "#fff",
                  WebkitTextFillColor: "#fff",
                },
              }}
            >
              {user ? "Open clipper" : "Explore the studio"}
            </Button>
          </Stack>
        </Container>
      </Box>

      {/* Final CTA */}
      <Box component="section" sx={{ py: { xs: 8, md: 11 }, bgcolor: "#FAFAFF" }}>
        <Container maxWidth="md">
          <Box
            component={motion.div}
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.45 }}
            sx={{
              textAlign: "center",
              p: { xs: 4, md: 6.5 },
              borderRadius: 5,
              position: "relative",
              overflow: "hidden",
              background: `linear-gradient(145deg, ${brandColors.sidebar} 0%, #1E1B4B 50%, #312E81 100%)`,
              color: "#F8FAFC",
              boxShadow: "0 28px 64px rgba(79, 70, 229, 0.28)",
              border: "1px solid rgba(255,255,255,0.08)",
              "&::before": {
                content: '""',
                position: "absolute",
                width: 320,
                height: 320,
                borderRadius: "50%",
                top: -100,
                right: -80,
                background: "radial-gradient(circle, rgba(109,40,217,0.55), transparent 70%)",
              },
              "&::after": {
                content: '""',
                position: "absolute",
                width: 240,
                height: 240,
                borderRadius: "50%",
                bottom: -80,
                left: -40,
                background: "radial-gradient(circle, rgba(6,182,212,0.3), transparent 70%)",
              },
            }}
          >
            <Box sx={{ position: "relative", zIndex: 1 }}>
              <Box
                sx={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 1,
                  px: 1.5,
                  py: 0.75,
                  mb: 2.5,
                  borderRadius: 999,
                  bgcolor: "rgba(255,255,255,0.08)",
                  border: "1px solid rgba(255,255,255,0.12)",
                }}
              >
                <AutoAwesomeIcon sx={{ fontSize: 16, color: brandColors.violetLight }} />
                <Typography
                  variant="caption"
                  fontWeight={800}
                  sx={{ color: "rgba(248,250,252,0.9)", WebkitTextFillColor: "rgba(248,250,252,0.9)" }}
                >
                  Start your first project in minutes
                </Typography>
              </Box>
              <Typography
                variant="h3"
                sx={{
                  fontWeight: 800,
                  letterSpacing: "-0.03em",
                  mb: 1.75,
                  fontSize: { xs: "1.85rem", md: "2.4rem" },
                  color: "#F8FAFC",
                  WebkitTextFillColor: "#F8FAFC",
                }}
              >
                Ready to build your next lesson?
              </Typography>
              <Typography
                sx={{
                  color: "rgba(226,232,240,0.78)",
                  WebkitTextFillColor: "rgba(226,232,240,0.78)",
                  mb: 3.75,
                  maxWidth: 460,
                  mx: "auto",
                  lineHeight: 1.7,
                }}
              >
                Open Naratto, drop in slides, generate AI voice, and export a professional learning
                video your audience will actually finish.
              </Typography>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} justifyContent="center">
                <WhiteCtaButton to={primaryCta} endIcon={<ArrowForwardIcon />}>
                  {primaryLabel}
                </WhiteCtaButton>
                {!user && (
                  <Button
                    component={RouterLink}
                    to="/login"
                    size="large"
                    variant="outlined"
                    sx={{
                      color: "#ffffff",
                      WebkitTextFillColor: "#ffffff",
                      borderColor: "rgba(255,255,255,0.5)",
                      "&:hover": {
                        borderColor: "#ffffff",
                        bgcolor: "rgba(255,255,255,0.1)",
                        color: "#ffffff",
                        WebkitTextFillColor: "#ffffff",
                      },
                    }}
                  >
                    I already have an account
                  </Button>
                )}
              </Stack>
            </Box>
          </Box>
        </Container>
      </Box>

      {/* Footer */}
      <Box
        component="footer"
        sx={{
          borderTop: "1px solid",
          borderColor: "divider",
          py: { xs: 4, md: 5 },
          bgcolor: "#fff",
        }}
      >
        <Container maxWidth="lg">
          <Box
            display="grid"
            gap={3}
            gridTemplateColumns={{ xs: "1fr", md: "1.4fr 1fr 1fr" }}
            alignItems="start"
          >
            <Box>
              <BrandLogo size="md" subtitle="Learning video studio" />
              <Typography
                variant="body2"
                sx={{
                  mt: 1.75,
                  maxWidth: 320,
                  color: brandColors.slate,
                  WebkitTextFillColor: brandColors.slate,
                  lineHeight: 1.65,
                }}
              >
                Turn slides and narration into polished educational videos—with AI voice, motion, and
                export-ready MP4s.
              </Typography>
            </Box>
            <Box>
              <Typography
                variant="subtitle2"
                fontWeight={800}
                sx={{ mb: 1.25, color: brandColors.ink, WebkitTextFillColor: brandColors.ink }}
              >
                Product
              </Typography>
              <Stack spacing={0.75} alignItems="flex-start">
                {navLinks.map((l) => (
                  <Button
                    key={l.href}
                    href={l.href}
                    size="small"
                    color="inherit"
                    sx={{
                      justifyContent: "flex-start",
                      px: 0,
                      minWidth: 0,
                      color: brandColors.slate,
                      WebkitTextFillColor: brandColors.slate,
                      fontWeight: 600,
                    }}
                  >
                    {l.label}
                  </Button>
                ))}
              </Stack>
            </Box>
            <Box>
              <Typography
                variant="subtitle2"
                fontWeight={800}
                sx={{ mb: 1.25, color: brandColors.ink, WebkitTextFillColor: brandColors.ink }}
              >
                Account
              </Typography>
              <Stack spacing={0.75} alignItems="flex-start">
                <Button
                  component={RouterLink}
                  to={user ? "/dashboard" : "/login"}
                  size="small"
                  color="inherit"
                  sx={{
                    justifyContent: "flex-start",
                    px: 0,
                    color: brandColors.slate,
                    WebkitTextFillColor: brandColors.slate,
                    fontWeight: 600,
                  }}
                >
                  {user ? "Dashboard" : "Sign in"}
                </Button>
                <Button
                  component={RouterLink}
                  to={user ? "/projects" : "/register"}
                  size="small"
                  color="inherit"
                  sx={{
                    justifyContent: "flex-start",
                    px: 0,
                    color: brandColors.slate,
                    WebkitTextFillColor: brandColors.slate,
                    fontWeight: 600,
                  }}
                >
                  {user ? "Projects" : "Create account"}
                </Button>
              </Stack>
            </Box>
          </Box>
          <Divider sx={{ my: 3.5 }} />
          <Stack
            direction={{ xs: "column", sm: "row" }}
            justifyContent="space-between"
            alignItems={{ xs: "flex-start", sm: "center" }}
            spacing={1}
          >
            <Typography
              variant="caption"
              sx={{ color: brandColors.slate, WebkitTextFillColor: brandColors.slate }}
            >
              © {new Date().getFullYear()} Naratto. All rights reserved.
            </Typography>
            <Typography
              variant="caption"
              fontWeight={600}
              sx={{ color: brandColors.violet, WebkitTextFillColor: brandColors.violet }}
            >
              Narrate once. Teach forever.
            </Typography>
          </Stack>
        </Container>
      </Box>
    </Box>
  );
}
