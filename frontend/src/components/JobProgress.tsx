import { useEffect, useState } from "react";
import { Box, Chip, LinearProgress, Stack, Typography } from "@mui/material";
import { elapsedSeconds, etaSeconds, formatDuration } from "./renderProgress";

type Phase = { id: string; label: string };

type Props = {
  active: boolean;
  mode: "waiting" | "working" | "done";
  progress: number;
  title: string;
  detail?: string;
  startedAt?: string | null;
  createdAt?: string | null;
  finishedAt?: string | null;
  phases?: Phase[];
  activePhase?: string;
  unknownTimeNote?: string;
};

export default function JobProgress({
  active,
  mode,
  progress,
  title,
  detail,
  startedAt,
  createdAt,
  finishedAt,
  phases,
  activePhase,
  unknownTimeNote = "Time left appears after the percent starts moving.",
}: Props) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [active]);

  const elapsed = elapsedSeconds(startedAt, createdAt, now, active ? null : finishedAt);
  const eta = etaSeconds(elapsed, progress, active && mode === "working");
  const determinate = progress > 0;
  const phaseIndex = phases?.findIndex((phase) => phase.id === activePhase) ?? -1;

  let clock = "";
  if (elapsed != null && mode === "waiting") clock = `Waiting ${formatDuration(elapsed)}`;
  else if (elapsed != null && mode === "working") clock = `Working for ${formatDuration(elapsed)}`;
  else if (elapsed != null && mode === "done" && finishedAt) clock = `Took ${formatDuration(elapsed)}`;
  if (eta != null) clock = clock ? `${clock} · about ${formatDuration(eta)} left` : `About ${formatDuration(eta)} left`;

  return (
    <Stack spacing={1.25}>
      <Stack direction="row" spacing={2} alignItems="flex-start" justifyContent="space-between">
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="subtitle1" fontWeight={800}>
            {title}
          </Typography>
          {detail && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
              {detail}
            </Typography>
          )}
        </Box>
        <Typography variant="h5" fontWeight={800} sx={{ flexShrink: 0, fontVariantNumeric: "tabular-nums" }}>
          {determinate ? `${Math.min(100, Math.max(0, progress))}%` : "…"}
        </Typography>
      </Stack>
      {phases && phases.length > 0 && (
        <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
          {phases.map((phase, index) => {
            const current = phase.id === activePhase;
            const past = phaseIndex >= 0 && index < phaseIndex;
            return (
              <Chip
                key={phase.id}
                size="small"
                label={phase.label}
                color={current ? "primary" : "default"}
                variant={current || past ? "filled" : "outlined"}
                sx={{ opacity: past || current ? 1 : 0.55 }}
              />
            );
          })}
        </Stack>
      )}
      <LinearProgress variant={determinate ? "determinate" : "indeterminate"} value={Math.min(100, progress)} />
      {clock && (
        <Typography variant="body2" sx={{ fontVariantNumeric: "tabular-nums" }}>
          {clock}
        </Typography>
      )}
      {active && mode === "working" && eta != null && (
        <Typography variant="caption" color="text.secondary">
          Approximate, from how fast the percent has moved so far. A model load or a quiet step can make this drift.
        </Typography>
      )}
      {active && mode === "working" && eta == null && (
        <Typography variant="caption" color="text.secondary">
          {unknownTimeNote}
        </Typography>
      )}
    </Stack>
  );
}
