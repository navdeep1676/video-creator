import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from "@mui/material";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import type { ReactNode } from "react";
import { brandColors } from "../theme";

export type ConfirmDialogTone = "danger" | "warning" | "info";

type Props = {
  open: boolean;
  title: string;
  description?: ReactNode;
  /** Optional highlighted name / detail under the description */
  highlight?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  loading?: boolean;
  tone?: ConfirmDialogTone;
  onClose: () => void;
  onConfirm: () => void;
};

const toneStyles: Record<
  ConfirmDialogTone,
  { iconBg: string; iconColor: string; confirmColor: "error" | "warning" | "primary"; Icon: typeof DeleteOutlineIcon }
> = {
  danger: {
    iconBg: "rgba(244, 63, 94, 0.12)",
    iconColor: brandColors.rose,
    confirmColor: "error",
    Icon: DeleteOutlineIcon,
  },
  warning: {
    iconBg: "rgba(245, 158, 11, 0.12)",
    iconColor: "#F59E0B",
    confirmColor: "warning",
    Icon: WarningAmberRoundedIcon,
  },
  info: {
    iconBg: "rgba(109, 40, 217, 0.1)",
    iconColor: brandColors.violet,
    confirmColor: "primary",
    Icon: InfoOutlinedIcon,
  },
};

export default function ConfirmDialog({
  open,
  title,
  description,
  highlight,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  loading,
  tone = "danger",
  onClose,
  onConfirm,
}: Props) {
  const t = toneStyles[tone];
  const Icon = t.Icon;

  return (
    <Dialog
      open={open}
      onClose={loading ? undefined : onClose}
      fullWidth
      maxWidth="xs"
      PaperProps={{
        sx: {
          borderRadius: 3,
          border: "1px solid",
          borderColor: "divider",
          overflow: "hidden",
        },
      }}
    >
      <DialogTitle sx={{ px: { xs: 2.5, sm: 3.5 }, pt: { xs: 2.75, sm: 3.25 }, pb: 1.5 }}>
        <Stack direction="row" spacing={1.75} alignItems="flex-start">
          <Box
            sx={{
              width: 44,
              height: 44,
              borderRadius: 2,
              display: "grid",
              placeItems: "center",
              bgcolor: t.iconBg,
              color: t.iconColor,
              flexShrink: 0,
            }}
          >
            <Icon />
          </Box>
          <Box sx={{ pt: 0.25, minWidth: 0 }}>
            <Typography variant="h6" fontWeight={800} sx={{ lineHeight: 1.3 }}>
              {title}
            </Typography>
          </Box>
        </Stack>
      </DialogTitle>
      <DialogContent
        sx={{
          px: { xs: 2.5, sm: 3.5 },
          pb: 1,
          "&.MuiDialogContent-root": {
            paddingTop: 0.5,
          },
        }}
      >
        {description && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: highlight ? 1.75 : 0.5 }}>
            {description}
          </Typography>
        )}
        {highlight && (
          <Box
            sx={{
              px: 1.75,
              py: 1.35,
              borderRadius: 2,
              bgcolor: "action.hover",
              border: "1px solid",
              borderColor: "divider",
            }}
          >
            <Typography variant="body2" fontWeight={700} noWrap title={highlight}>
              {highlight}
            </Typography>
          </Box>
        )}
      </DialogContent>
      <DialogActions sx={{ px: { xs: 2.5, sm: 3.5 }, pb: { xs: 2.5, sm: 3 }, pt: 1.5, gap: 1.25 }}>
        <Button onClick={onClose} disabled={loading} color="inherit" sx={{ borderRadius: 2 }}>
          {cancelLabel}
        </Button>
        <Button
          variant="contained"
          color={t.confirmColor}
          disabled={loading}
          onClick={onConfirm}
          sx={{ borderRadius: 2, minWidth: 110 }}
        >
          {loading ? "Working…" : confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
