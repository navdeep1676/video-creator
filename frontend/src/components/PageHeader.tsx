import { Box, Breadcrumbs, Link, Stack, Typography } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import NavigateNextIcon from "@mui/icons-material/NavigateNext";
import { motion } from "framer-motion";

export type Crumb = {
  label: string;
  to?: string;
};

type Props = {
  title: string;
  subtitle?: string;
  crumbs?: Crumb[];
  actions?: React.ReactNode;
};

export default function PageHeader({ title, subtitle, crumbs, actions }: Props) {
  return (
    <Stack
      component={motion.div}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      spacing={1.5}
      sx={{ mb: 0.5 }}
    >
      {crumbs && crumbs.length > 0 && (
        <Breadcrumbs separator={<NavigateNextIcon fontSize="small" />} aria-label="breadcrumb">
          {crumbs.map((c, i) =>
            c.to && i < crumbs.length - 1 ? (
              <Link
                key={`${c.label}-${i}`}
                component={RouterLink}
                to={c.to}
                underline="hover"
                color="inherit"
                variant="body2"
                sx={{ fontWeight: 500 }}
              >
                {c.label}
              </Link>
            ) : (
              <Typography key={`${c.label}-${i}`} color="text.primary" variant="body2" fontWeight={600}>
                {c.label}
              </Typography>
            )
          )}
        </Breadcrumbs>
      )}
      <Stack
        direction={{ xs: "column", sm: "row" }}
        justifyContent="space-between"
        alignItems={{ xs: "stretch", sm: "flex-start" }}
        spacing={2}
      >
        <Box>
          <Typography
            variant="h4"
            component="h1"
            sx={{
              color: "text.primary",
              WebkitTextFillColor: "currentColor",
              fontWeight: 800,
              letterSpacing: "-0.025em",
            }}
          >
            {title}
          </Typography>
          {subtitle && (
            <Typography color="text.secondary" sx={{ mt: 0.75, maxWidth: 560 }}>
              {subtitle}
            </Typography>
          )}
        </Box>
        {actions && (
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {actions}
          </Stack>
        )}
      </Stack>
    </Stack>
  );
}
