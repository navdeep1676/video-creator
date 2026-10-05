import { alpha, createTheme } from "@mui/material/styles";

/** Naratto brand palette — narration-first learning video studio */
const brand = {
  violet: "#6D28D9",
  violetDark: "#5B21B6",
  violetLight: "#8B5CF6",
  indigo: "#4F46E5",
  cyan: "#06B6D4",
  rose: "#F43F5E",
  ink: "#0F172A",
  slate: "#64748B",
  mist: "#F1F5F9",
  paper: "#FFFFFF",
  sidebar: "#0B1020",
  sidebarElevated: "#12182B",
  sidebarBorder: "rgba(148, 163, 184, 0.12)",
};

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: brand.violet,
      dark: brand.violetDark,
      light: brand.violetLight,
      contrastText: "#fff",
    },
    secondary: {
      main: brand.cyan,
      contrastText: "#fff",
    },
    error: { main: brand.rose },
    success: { main: "#10B981" },
    warning: { main: "#F59E0B" },
    info: { main: brand.indigo },
    background: {
      default: "#F5F3FF",
      paper: brand.paper,
    },
    text: {
      primary: brand.ink,
      secondary: brand.slate,
    },
    divider: "rgba(15, 23, 42, 0.08)",
  },
  typography: {
    fontFamily: '"Plus Jakarta Sans", "Noto Sans Devanagari", "DM Sans", "Helvetica", "Arial", sans-serif',
    h3: { fontWeight: 800, letterSpacing: "-0.03em" },
    h4: { fontWeight: 800, letterSpacing: "-0.025em" },
    h5: { fontWeight: 700, letterSpacing: "-0.02em" },
    h6: { fontWeight: 700, letterSpacing: "-0.015em" },
    subtitle1: { fontWeight: 600 },
    subtitle2: { fontWeight: 600 },
    button: { fontWeight: 700, letterSpacing: "0.01em" },
    body1: { lineHeight: 1.6 },
    body2: { lineHeight: 1.55 },
  },
  shape: { borderRadius: 14 },
  shadows: [
    "none",
    "0 1px 2px rgba(15, 23, 42, 0.04)",
    "0 2px 8px rgba(15, 23, 42, 0.05)",
    "0 4px 16px rgba(15, 23, 42, 0.06)",
    "0 8px 24px rgba(15, 23, 42, 0.07)",
    "0 12px 32px rgba(15, 23, 42, 0.08)",
    "0 16px 40px rgba(15, 23, 42, 0.09)",
    "0 20px 48px rgba(15, 23, 42, 0.1)",
    "0 24px 56px rgba(15, 23, 42, 0.11)",
    "0 28px 64px rgba(15, 23, 42, 0.12)",
    "0 32px 72px rgba(15, 23, 42, 0.13)",
    "0 36px 80px rgba(15, 23, 42, 0.14)",
    "0 40px 88px rgba(15, 23, 42, 0.15)",
    "0 44px 96px rgba(15, 23, 42, 0.16)",
    "0 48px 104px rgba(15, 23, 42, 0.17)",
    "0 52px 112px rgba(15, 23, 42, 0.18)",
    "0 56px 120px rgba(15, 23, 42, 0.19)",
    "0 60px 128px rgba(15, 23, 42, 0.2)",
    "0 64px 136px rgba(15, 23, 42, 0.21)",
    "0 68px 144px rgba(15, 23, 42, 0.22)",
    "0 72px 152px rgba(15, 23, 42, 0.23)",
    "0 76px 160px rgba(15, 23, 42, 0.24)",
    "0 80px 168px rgba(15, 23, 42, 0.25)",
    "0 84px 176px rgba(15, 23, 42, 0.26)",
    "0 88px 184px rgba(15, 23, 42, 0.27)",
  ],
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundImage:
            "radial-gradient(ellipse 80% 50% at 50% -20%, rgba(109, 40, 217, 0.12), transparent)," +
            "radial-gradient(ellipse 60% 40% at 100% 0%, rgba(6, 182, 212, 0.08), transparent)",
          backgroundAttachment: "fixed",
          // Reset fill so gradient titles don't leave buttons with invisible labels
          WebkitTextFillColor: "initial",
        },
        "button, a.MuiButton-root, .MuiButton-root, .MuiChip-root, .MuiChip-label": {
          WebkitTextFillColor: "currentColor",
        },
        "@keyframes naratto-fade-up": {
          from: { opacity: 0, transform: "translateY(10px)" },
          to: { opacity: 1, transform: "translateY(0)" },
        },
        "@keyframes naratto-shimmer": {
          "0%": { backgroundPosition: "200% 0" },
          "100%": { backgroundPosition: "-200% 0" },
        },
        "@keyframes naratto-pulse-soft": {
          "0%, 100%": { opacity: 1 },
          "50%": { opacity: 0.7 },
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          textTransform: "none",
          fontWeight: 700,
          borderRadius: 12,
          paddingInline: 18,
          // Always paint label/icons with CSS color (avoids invisible text from fill/gradient inheritance)
          WebkitTextFillColor: "currentColor",
          transition:
            "transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease, background-color 0.18s ease, color 0.18s ease",
          "&:active": { transform: "scale(0.98)" },
          "& .MuiButton-startIcon, & .MuiButton-endIcon": {
            color: "inherit",
            WebkitTextFillColor: "currentColor",
          },
          "& .MuiSvgIcon-root": {
            color: "inherit",
            fill: "currentColor",
          },
        },
        contained: {
          color: "#ffffff",
          WebkitTextFillColor: "#ffffff",
          "&:hover": {
            color: "#ffffff",
            WebkitTextFillColor: "#ffffff",
          },
          "&.Mui-disabled": {
            color: "rgba(255, 255, 255, 0.85)",
            WebkitTextFillColor: "rgba(255, 255, 255, 0.85)",
            opacity: 0.72,
          },
        },
        containedPrimary: {
          color: "#ffffff",
          WebkitTextFillColor: "#ffffff",
          backgroundColor: brand.violet,
          backgroundImage: `linear-gradient(135deg, ${brand.violet} 0%, ${brand.indigo} 100%)`,
          boxShadow: `0 8px 20px ${alpha(brand.violet, 0.28)}`,
          "&:hover": {
            color: "#ffffff",
            WebkitTextFillColor: "#ffffff",
            backgroundColor: brand.violetDark,
            backgroundImage: `linear-gradient(135deg, ${brand.violetDark} 0%, ${brand.violet} 100%)`,
            boxShadow: `0 10px 28px ${alpha(brand.violet, 0.35)}`,
          },
          "&.Mui-disabled": {
            color: "#ffffff",
            WebkitTextFillColor: "#ffffff",
            backgroundImage: "none",
            backgroundColor: alpha(brand.violet, 0.45),
          },
        },
        containedSecondary: {
          color: "#ffffff",
          WebkitTextFillColor: "#ffffff",
          backgroundColor: brand.cyan,
          backgroundImage: `linear-gradient(135deg, ${brand.cyan} 0%, #0EA5E9 100%)`,
          "&:hover": {
            color: "#ffffff",
            WebkitTextFillColor: "#ffffff",
            backgroundColor: "#0891B2",
            backgroundImage: `linear-gradient(135deg, #0891B2 0%, ${brand.cyan} 100%)`,
          },
        },
        containedError: {
          color: "#ffffff",
          WebkitTextFillColor: "#ffffff",
        },
        containedSuccess: {
          color: "#ffffff",
          WebkitTextFillColor: "#ffffff",
        },
        outlined: {
          borderWidth: 1.5,
          backgroundColor: "rgba(255, 255, 255, 0.72)",
          "&:hover": {
            borderWidth: 1.5,
            backgroundColor: alpha(brand.violet, 0.06),
          },
          "&.Mui-disabled": {
            borderColor: alpha(brand.ink, 0.12),
            color: alpha(brand.ink, 0.38),
            WebkitTextFillColor: alpha(brand.ink, 0.38),
          },
        },
        outlinedPrimary: {
          color: brand.violet,
          WebkitTextFillColor: brand.violet,
          borderColor: alpha(brand.violet, 0.45),
          "&:hover": {
            color: brand.violetDark,
            WebkitTextFillColor: brand.violetDark,
            borderColor: brand.violet,
            backgroundColor: alpha(brand.violet, 0.08),
          },
        },
        outlinedSecondary: {
          color: "#0E7490",
          WebkitTextFillColor: "#0E7490",
          borderColor: alpha(brand.cyan, 0.55),
        },
        text: {
          WebkitTextFillColor: "currentColor",
        },
        textPrimary: {
          color: brand.violet,
          WebkitTextFillColor: brand.violet,
          "&:hover": {
            color: brand.violetDark,
            WebkitTextFillColor: brand.violetDark,
            backgroundColor: alpha(brand.violet, 0.08),
          },
        },
        textInherit: {
          color: "inherit",
          WebkitTextFillColor: "currentColor",
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 18,
          border: "1px solid",
          borderColor: "rgba(15, 23, 42, 0.06)",
          boxShadow: "0 8px 28px rgba(15, 23, 42, 0.05)",
          backgroundImage: "linear-gradient(180deg, rgba(255,255,255,0.9) 0%, #fff 100%)",
          transition: "transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease",
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
        },
        rounded: {
          borderRadius: 16,
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          fontWeight: 600,
          borderRadius: 8,
          WebkitTextFillColor: "currentColor",
        },
        filled: {
          "&.MuiChip-colorPrimary": {
            color: "#ffffff",
            WebkitTextFillColor: "#ffffff",
            backgroundColor: brand.violet,
          },
          "&.MuiChip-colorSecondary": {
            color: "#ffffff",
            WebkitTextFillColor: "#ffffff",
          },
          "&.MuiChip-colorSuccess": {
            color: "#ffffff",
            WebkitTextFillColor: "#ffffff",
          },
          "&.MuiChip-colorError": {
            color: "#ffffff",
            WebkitTextFillColor: "#ffffff",
          },
          "&.MuiChip-colorWarning": {
            color: brand.ink,
            WebkitTextFillColor: brand.ink,
          },
          "&.MuiChip-colorInfo": {
            color: "#ffffff",
            WebkitTextFillColor: "#ffffff",
          },
        },
        outlined: {
          WebkitTextFillColor: "currentColor",
        },
        icon: {
          color: "inherit",
        },
      },
    },
    MuiTextField: {
      defaultProps: { size: "medium" },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          transition: "box-shadow 0.18s ease",
          "&.Mui-focused": {
            boxShadow: `0 0 0 3px ${alpha(brand.violet, 0.15)}`,
          },
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          borderRadius: 20,
          border: "1px solid rgba(15, 23, 42, 0.06)",
          boxShadow: "0 24px 64px rgba(15, 23, 42, 0.16)",
        },
      },
    },
    MuiDialogTitle: {
      styleOverrides: {
        root: {
          fontWeight: 800,
          letterSpacing: "-0.02em",
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backdropFilter: "blur(12px)",
          backgroundColor: "rgba(255, 255, 255, 0.82)",
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          transition: "all 0.18s ease",
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          height: 8,
          backgroundColor: alpha(brand.violet, 0.1),
        },
        bar: {
          borderRadius: 8,
          background: `linear-gradient(90deg, ${brand.violet}, ${brand.cyan})`,
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          borderRadius: 8,
          fontWeight: 600,
          fontSize: 12,
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          transition: "transform 0.15s ease, background 0.15s ease",
          "&:hover": { transform: "scale(1.06)" },
          "&:active": { transform: "scale(0.96)" },
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: 12,
        },
      },
    },
  },
});

export const brandColors = brand;
