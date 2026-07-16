import { Box, Breadcrumbs, Link, Stack, Typography } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import NavigateNextIcon from "@mui/icons-material/NavigateNext";

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
    <Stack spacing={1.5} sx={{ mb: 1 }}>
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
              >
                {c.label}
              </Link>
            ) : (
              <Typography key={`${c.label}-${i}`} color="text.primary" variant="body2">
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
          <Typography variant="h4" component="h1">
            {title}
          </Typography>
          {subtitle && (
            <Typography color="text.secondary" sx={{ mt: 0.5 }}>
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
