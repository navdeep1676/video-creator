import { Box, Typography } from "@mui/material";
import { brandColors } from "../theme";

type Props = {
  size?: "sm" | "md" | "lg";
  inverted?: boolean;
  showWordmark?: boolean;
  subtitle?: string;
};

const sizes = {
  sm: { mark: 28, font: "1rem", gap: 1 },
  md: { mark: 36, font: "1.15rem", gap: 1.25 },
  lg: { mark: 48, font: "1.5rem", gap: 1.5 },
};

/** Naratto monogram mark + wordmark */
export default function BrandLogo({
  size = "md",
  inverted = false,
  showWordmark = true,
  subtitle,
}: Props) {
  const s = sizes[size];
  const textColor = inverted ? "#F8FAFC" : brandColors.ink;
  const muted = inverted ? "rgba(248, 250, 252, 0.55)" : brandColors.slate;

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: s.gap, minWidth: 0 }}>
      <Box
        sx={{
          width: s.mark,
          height: s.mark,
          borderRadius: size === "lg" ? 2.5 : 2,
          flexShrink: 0,
          background: `linear-gradient(145deg, ${brandColors.violetLight} 0%, ${brandColors.violet} 45%, ${brandColors.indigo} 100%)`,
          boxShadow: inverted
            ? "0 8px 24px rgba(109, 40, 217, 0.45)"
            : "0 8px 20px rgba(109, 40, 217, 0.3)",
          display: "grid",
          placeItems: "center",
          position: "relative",
          overflow: "hidden",
          "&::after": {
            content: '""',
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(135deg, rgba(255,255,255,0.28) 0%, transparent 50%)",
          },
        }}
        aria-hidden
      >
        <Box
          component="svg"
          viewBox="0 0 24 24"
          sx={{ width: s.mark * 0.55, height: s.mark * 0.55, zIndex: 1 }}
        >
          <path
            fill="#fff"
            d="M4 16.5V7.5c0-.8.9-1.3 1.6-.9l6.2 3.7c.6.4.6 1.3 0 1.7l-6.2 3.7c-.7.4-1.6-.1-1.6-.9z"
            opacity={0.95}
          />
          <path
            fill="#fff"
            d="M13 8.2c0-.5.5-.8.9-.6l5.4 3.2c.4.2.4.8 0 1L13.9 15c-.4.2-.9-.1-.9-.6V8.2z"
            opacity={0.75}
          />
        </Box>
      </Box>
      {showWordmark && (
        <Box minWidth={0}>
          <Typography
            sx={{
              fontWeight: 800,
              fontSize: s.font,
              letterSpacing: "-0.03em",
              lineHeight: 1.15,
              color: textColor,
            }}
          >
            Naratto
          </Typography>
          {subtitle && (
            <Typography
              variant="caption"
              sx={{ color: muted, display: "block", lineHeight: 1.2, fontWeight: 500 }}
            >
              {subtitle}
            </Typography>
          )}
        </Box>
      )}
    </Box>
  );
}
