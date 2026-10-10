import { useMemo, useState } from "react";
import {
  AppBar,
  Avatar,
  Box,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import MenuIcon from "@mui/icons-material/Menu";
import DashboardOutlinedIcon from "@mui/icons-material/DashboardOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import ContentCutIcon from "@mui/icons-material/ContentCut";
import LogoutIcon from "@mui/icons-material/Logout";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import { Link as RouterLink, Outlet, NavLink, useLocation, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "../auth/AuthContext";
import BrandLogo from "./BrandLogo";
import SystemMonitor from "./SystemMonitor";
import { brandColors } from "../theme";

const DRAWER_WIDTH = 268;

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: <DashboardOutlinedIcon fontSize="small" />, end: true, hint: "Overview" },
  { to: "/projects", label: "Projects", icon: <FolderOutlinedIcon fontSize="small" />, hint: "Your videos" },
  { to: "/clipper", label: "Video Clipper", icon: <ContentCutIcon fontSize="small" />, hint: "Extract slides" },
  { to: "/settings", label: "Settings", icon: <SettingsOutlinedIcon fontSize="small" />, hint: "Account" },
];

function pageTitle(pathname: string): string {
  if (pathname === "/dashboard" || pathname === "/dashboard/") return "Dashboard";
  if (pathname.startsWith("/projects") && pathname.includes("/export")) return "Export";
  if (pathname.startsWith("/projects/") && pathname !== "/projects") return "Project studio";
  if (pathname.startsWith("/projects")) return "Projects";
  if (pathname.startsWith("/clipper")) return "Video Clipper";
  if (pathname.startsWith("/settings")) return "Settings";
  return "Naratto";
}

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const [mobileOpen, setMobileOpen] = useState(false);

  const initials = useMemo(() => {
    const name = user?.display_name || user?.email || "?";
    return name
      .split(/[\s@]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase())
      .join("");
  }, [user]);

  const drawer = (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: `linear-gradient(180deg, ${brandColors.sidebar} 0%, #0A0F1C 55%, #0D1324 100%)`,
        color: "#E2E8F0",
        position: "relative",
        overflow: "hidden",
        "&::before": {
          content: '""',
          position: "absolute",
          top: -80,
          right: -60,
          width: 220,
          height: 220,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(109,40,217,0.35) 0%, transparent 70%)",
          pointerEvents: "none",
        },
        "&::after": {
          content: '""',
          position: "absolute",
          bottom: 80,
          left: -40,
          width: 160,
          height: 160,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(6,182,212,0.15) 0%, transparent 70%)",
          pointerEvents: "none",
        },
      }}
    >
      <Toolbar sx={{ px: 2.5, py: 1.5, minHeight: 72 }}>
        <Box
          component={RouterLink}
          to="/"
          sx={{ textDecoration: "none", color: "inherit", display: "block" }}
        >
          <BrandLogo inverted subtitle="Learning video studio" size="md" />
        </Box>
      </Toolbar>

      <Box sx={{ px: 2, pb: 1.5 }}>
        <Box
          sx={{
            px: 1.5,
            py: 1.25,
            borderRadius: 2.5,
            border: `1px solid ${brandColors.sidebarBorder}`,
            background: "linear-gradient(135deg, rgba(109,40,217,0.22) 0%, rgba(6,182,212,0.08) 100%)",
            display: "flex",
            alignItems: "center",
            gap: 1,
          }}
        >
          <AutoAwesomeIcon sx={{ fontSize: 18, color: brandColors.violetLight }} />
          <Box>
            <Typography variant="caption" sx={{ color: "rgba(248,250,252,0.9)", fontWeight: 700, display: "block" }}>
              AI narration ready
            </Typography>
            <Typography variant="caption" sx={{ color: "rgba(148,163,184,0.9)", fontSize: 11 }}>
              Slides → voice → MP4
            </Typography>
          </Box>
        </Box>
      </Box>

      <Typography
        variant="caption"
        sx={{
          px: 3,
          pt: 1,
          pb: 0.75,
          color: "rgba(148,163,184,0.7)",
          fontWeight: 700,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          fontSize: 10,
        }}
      >
        Menu
      </Typography>

      <List sx={{ px: 1.5, py: 0.5, flex: 1, position: "relative", zIndex: 1 }}>
        {navItems.map((item) => {
          const selected = item.end
            ? location.pathname === item.to
            : location.pathname === item.to || location.pathname.startsWith(`${item.to}/`);
          return (
            <ListItemButton
              key={item.to}
              component={NavLink}
              to={item.to}
              end={item.end}
              selected={selected}
              onClick={() => setMobileOpen(false)}
              sx={{
                borderRadius: 2.5,
                mb: 0.6,
                py: 1.15,
                px: 1.5,
                color: selected ? "#fff" : "rgba(226,232,240,0.78)",
                background: selected
                  ? `linear-gradient(135deg, ${brandColors.violet} 0%, ${brandColors.indigo} 100%)`
                  : "transparent",
                boxShadow: selected ? "0 8px 22px rgba(109, 40, 217, 0.35)" : "none",
                position: "relative",
                overflow: "hidden",
                "&:hover": {
                  bgcolor: selected ? undefined : "rgba(255,255,255,0.06)",
                  color: "#fff",
                },
                "&.Mui-selected:hover": {
                  background: `linear-gradient(135deg, ${brandColors.violetDark} 0%, ${brandColors.violet} 100%)`,
                },
                transition: "all 0.2s ease",
              }}
            >
              {selected && (
                <Box
                  component={motion.div}
                  layoutId="nav-glow"
                  sx={{
                    position: "absolute",
                    inset: 0,
                    background: "linear-gradient(90deg, rgba(255,255,255,0.12), transparent 60%)",
                    pointerEvents: "none",
                  }}
                />
              )}
              <ListItemIcon
                sx={{
                  minWidth: 38,
                  color: selected ? "#fff" : "rgba(148,163,184,0.95)",
                }}
              >
                {item.icon}
              </ListItemIcon>
              <ListItemText
                primary={item.label}
                secondary={item.hint}
                primaryTypographyProps={{ fontWeight: 700, fontSize: 14 }}
                secondaryTypographyProps={{
                  sx: {
                    color: selected ? "rgba(255,255,255,0.7)" : "rgba(148,163,184,0.65)",
                    fontSize: 11,
                    mt: 0.15,
                  },
                }}
              />
            </ListItemButton>
          );
        })}
      </List>

      <Box sx={{ p: 2, position: "relative", zIndex: 1 }}>
        <Divider sx={{ borderColor: brandColors.sidebarBorder, mb: 2 }} />
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1.25,
            mb: 1.25,
            p: 1.25,
            borderRadius: 2.5,
            border: `1px solid ${brandColors.sidebarBorder}`,
            bgcolor: "rgba(255,255,255,0.03)",
          }}
        >
          <Avatar
            sx={{
              width: 38,
              height: 38,
              fontSize: 13,
              fontWeight: 700,
              background: `linear-gradient(135deg, ${brandColors.violetLight}, ${brandColors.cyan})`,
            }}
          >
            {initials}
          </Avatar>
          <Box minWidth={0} flex={1}>
            <Typography variant="body2" fontWeight={700} noWrap sx={{ color: "#F8FAFC" }}>
              {user?.display_name || "User"}
            </Typography>
            <Typography variant="caption" noWrap display="block" sx={{ color: "rgba(148,163,184,0.85)" }}>
              {user?.email}
            </Typography>
          </Box>
        </Box>
        <ListItemButton
          onClick={async () => {
            await logout();
            navigate("/");
          }}
          sx={{
            borderRadius: 2.5,
            color: "rgba(226,232,240,0.8)",
            border: `1px solid ${brandColors.sidebarBorder}`,
            "&:hover": {
              bgcolor: "rgba(244, 63, 94, 0.12)",
              color: "#FDA4AF",
              borderColor: "rgba(244, 63, 94, 0.25)",
            },
          }}
        >
          <ListItemIcon sx={{ minWidth: 38, color: "inherit" }}>
            <LogoutIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary="Log out" primaryTypographyProps={{ fontWeight: 600, fontSize: 14 }} />
        </ListItemButton>
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <AppBar
        position="fixed"
        elevation={0}
        color="inherit"
        sx={{
          borderBottom: "1px solid",
          borderColor: "divider",
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          ml: { md: `${DRAWER_WIDTH}px` },
        }}
      >
        <Toolbar sx={{ gap: 1.5, minHeight: { xs: 64, md: 68 } }}>
          {isMobile && (
            <IconButton edge="start" onClick={() => setMobileOpen(true)} aria-label="Open menu">
              <MenuIcon />
            </IconButton>
          )}
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
            <Typography variant="h6" fontWeight={800} letterSpacing="-0.02em" noWrap>
              {pageTitle(location.pathname)}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: { xs: "none", sm: "block" } }}>
              Turn slides into polished learning videos
            </Typography>
          </Box>
          {!isMobile && (
            <Tooltip title={user?.email || ""}>
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 1.25,
                  px: 1.5,
                  py: 0.75,
                  borderRadius: 999,
                  border: "1px solid",
                  borderColor: "divider",
                  bgcolor: "rgba(255,255,255,0.7)",
                }}
              >
                <Avatar
                  sx={{
                    width: 30,
                    height: 30,
                    fontSize: 12,
                    fontWeight: 700,
                    background: `linear-gradient(135deg, ${brandColors.violet}, ${brandColors.cyan})`,
                  }}
                >
                  {initials}
                </Avatar>
                <Typography variant="body2" fontWeight={600} color="text.secondary" noWrap>
                  {user?.display_name || user?.email}
                </Typography>
              </Box>
            </Tooltip>
          )}
        </Toolbar>
      </AppBar>

      <Box component="nav" sx={{ width: { md: DRAWER_WIDTH }, flexShrink: { md: 0 } }}>
        {isMobile ? (
          <Drawer
            variant="temporary"
            open={mobileOpen}
            onClose={() => setMobileOpen(false)}
            ModalProps={{ keepMounted: true }}
            sx={{
              "& .MuiDrawer-paper": {
                width: DRAWER_WIDTH,
                boxSizing: "border-box",
                border: "none",
              },
            }}
          >
            {drawer}
          </Drawer>
        ) : (
          <Drawer
            variant="permanent"
            open
            sx={{
              "& .MuiDrawer-paper": {
                width: DRAWER_WIDTH,
                boxSizing: "border-box",
                border: "none",
                boxShadow: "8px 0 32px rgba(15, 23, 42, 0.08)",
              },
            }}
          >
            {drawer}
          </Drawer>
        )}
      </Box>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          minWidth: 0,
        }}
      >
        <Toolbar sx={{ minHeight: { xs: 64, md: 68 } }} />
        <Box
          sx={{
            position: "sticky",
            top: { xs: 64, md: 68 },
            zIndex: (t) => t.zIndex.appBar - 1,
            px: { xs: 2, sm: 3 },
            pt: 2,
            pb: 0.5,
            bgcolor: "background.default",
          }}
        >
          <Box sx={{ maxWidth: 1200, mx: "auto" }}>
            <SystemMonitor />
          </Box>
        </Box>
        <Box sx={{ px: { xs: 2, sm: 3 }, pt: 1.5, pb: { xs: 2, sm: 3 }, maxWidth: 1200, mx: "auto" }}>
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </Box>
      </Box>
    </Box>
  );
}
