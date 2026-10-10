import { Box, Chip, LinearProgress, Paper, Skeleton, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { Link as RouterLink } from "react-router-dom";
import { api } from "../api/client";
import { brandColors } from "../theme";

type Meter = {
  percent: number | null;
};

type Ram = Meter & {
  used: number | null;
  total: number | null;
};

type Gpu = {
  available: boolean;
  utilization: number | null;
  vram_used: number | null;
  vram_total: number | null;
  temperature: number | null;
};

type Job = {
  id: string;
  kind: string;
  label: string;
  project_title: string;
  status: "queued" | "running";
  progress: number;
  detail: string | null;
  uses_gpu: boolean;
  on_gpu: boolean;
  href: string;
};

type GpuProcess = {
  pid: number;
  name: string;
  utilization: number;
  vram_used: number;
  on_gpu: boolean;
};

type Snapshot = {
  cpu: Meter;
  ram: Ram;
  gpu: Gpu;
  jobs: Job[];
  processes: GpuProcess[];
};

type Row = {
  id: string;
  chip: string;
  chipColor: "primary" | "default" | "warning";
  title: string;
  detail: string | null;
  progress: number | null;
  indeterminate: boolean;
  href?: string;
};

function formatBytes(value: number | null | undefined): string | null {
  if (value == null || Number.isNaN(value)) return null;
  const gb = value / 1024 ** 3;
  if (gb >= 10) return `${gb.toFixed(1)} GB`;
  if (gb >= 0.1) return `${gb.toFixed(2)} GB`;
  return `${Math.max(1, Math.round(value / 1024 ** 2))} MB`;
}

function percentText(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value)}%`;
}

function jobChip(job: Job): Pick<Row, "chip" | "chipColor"> {
  if (job.on_gpu) return { chip: "On GPU", chipColor: "primary" };
  if (job.status === "queued" && job.uses_gpu) return { chip: "Waiting · GPU", chipColor: "warning" };
  if (job.status === "queued") return { chip: "Waiting", chipColor: "warning" };
  return { chip: "CPU", chipColor: "default" };
}

function jobRow(job: Job): Row {
  const chip = jobChip(job);
  const title = job.project_title ? `${job.label} · ${job.project_title}` : job.label;
  return {
    id: job.id,
    ...chip,
    title,
    detail: job.detail,
    progress: job.progress,
    indeterminate: job.status === "running" && job.progress <= 0,
    href: job.href,
  };
}

function processRow(process: GpuProcess): Row {
  const vram = formatBytes(process.vram_used);
  const busy = process.utilization >= 2;
  return {
    id: `pid:${process.pid}`,
    chip: "On GPU",
    chipColor: "primary",
    title: process.name,
    detail: vram ? `${vram} VRAM` : null,
    progress: busy ? process.utilization : null,
    indeterminate: false,
  };
}

function MeterBlock({
  label,
  value,
  caption,
  color,
}: {
  label: string;
  value: string;
  caption: string;
  color: string;
}) {
  const numeric = value.endsWith("%") ? Number(value.replace("%", "")) : null;
  return (
    <Box sx={{ flex: "1 1 140px", minWidth: 0 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="baseline" spacing={1}>
        <Typography variant="caption" sx={{ fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase" }}>
          {label}
        </Typography>
        <Typography variant="body2" fontWeight={800} sx={{ fontVariantNumeric: "tabular-nums" }}>
          {value}
        </Typography>
      </Stack>
      <LinearProgress
        variant="determinate"
        value={numeric == null ? 0 : Math.max(0, Math.min(100, numeric))}
        sx={{
          mt: 0.5,
          height: 6,
          borderRadius: 99,
          bgcolor: "rgba(15, 23, 42, 0.06)",
          "& .MuiLinearProgress-bar": { bgcolor: color, borderRadius: 99 },
        }}
      />
      <Typography variant="caption" color="text.secondary" noWrap display="block" sx={{ mt: 0.35 }}>
        {caption}
      </Typography>
    </Box>
  );
}

function WorkRow({ row }: { row: Row }) {
  const title = (
    <Typography variant="body2" fontWeight={700} noWrap>
      {row.title}
    </Typography>
  );
  return (
    <Box sx={{ minWidth: 0 }}>
      <Stack direction="row" spacing={1} alignItems="center">
        <Chip size="small" label={row.chip} color={row.chipColor} variant={row.chipColor === "default" ? "outlined" : "filled"} />
        <Box sx={{ minWidth: 0, flex: 1 }}>
          {row.href ? (
            <Box component={RouterLink} to={row.href} sx={{ color: "inherit", textDecoration: "none", "&:hover": { textDecoration: "underline" } }}>
              {title}
            </Box>
          ) : (
            title
          )}
          {row.detail && (
            <Typography variant="caption" color="text.secondary" noWrap display="block">
              {row.detail}
            </Typography>
          )}
        </Box>
        <Typography variant="body2" fontWeight={800} sx={{ flexShrink: 0, fontVariantNumeric: "tabular-nums" }}>
          {row.indeterminate ? "…" : row.progress == null ? "" : percentText(row.progress)}
        </Typography>
      </Stack>
      {row.progress != null && (
        <LinearProgress
          variant={row.indeterminate ? "indeterminate" : "determinate"}
          value={row.indeterminate ? undefined : Math.max(0, Math.min(100, row.progress))}
          sx={{ mt: 0.6, height: 4, borderRadius: 99 }}
        />
      )}
    </Box>
  );
}

export default function SystemMonitor() {
  const query = useQuery({
    queryKey: ["system-monitor"],
    queryFn: async () => (await api.get<Snapshot>("/system")).data,
    refetchInterval: 2000,
    refetchIntervalInBackground: false,
    staleTime: 1000,
  });

  const data = query.data;
  const gpuValue = percentText(data?.gpu.utilization);
  const vramUsed = formatBytes(data?.gpu.vram_used);
  const vramTotal = formatBytes(data?.gpu.vram_total);
  const gpuCaption = vramUsed ? (vramTotal ? `${vramUsed} / ${vramTotal}` : `${vramUsed} VRAM`) : "VRAM";
  const ramUsed = formatBytes(data?.ram.used);
  const ramTotal = formatBytes(data?.ram.total);
  const ramCaption = ramUsed && ramTotal ? `${ramUsed} / ${ramTotal}` : "Memory";

  const onGpu: Row[] = [
    ...(data?.jobs.filter((job) => job.on_gpu).map(jobRow) ?? []),
    ...(data?.processes.map(processRow) ?? []),
  ];
  const offGpu: Row[] = data?.jobs.filter((job) => !job.on_gpu).map(jobRow) ?? [];
  const showWork = query.isSuccess;
  const anyWork = onGpu.length + offGpu.length > 0;

  return (
    <Paper
      component="section"
      aria-label="GPU, CPU, and RAM"
      elevation={0}
      sx={{
        px: { xs: 1.5, sm: 2 },
        py: 1.25,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 3,
        background: "rgba(255,255,255,0.92)",
      }}
    >
      {query.isLoading && !data ? (
        <Stack direction="row" spacing={2}>
          <Skeleton variant="rounded" height={44} sx={{ flex: 1 }} />
          <Skeleton variant="rounded" height={44} sx={{ flex: 1 }} />
          <Skeleton variant="rounded" height={44} sx={{ flex: 1 }} />
        </Stack>
      ) : query.isError && !data ? (
        <Typography variant="body2" color="text.secondary">
          System monitor is unavailable.
        </Typography>
      ) : (
        <Stack spacing={1.25}>
          <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
            <MeterBlock label="GPU" value={gpuValue} caption={gpuCaption} color={brandColors.violet} />
            <MeterBlock label="CPU" value={percentText(data?.cpu.percent)} caption="Processor" color={brandColors.cyan} />
            <MeterBlock label="RAM" value={percentText(data?.ram.percent)} caption={ramCaption} color={brandColors.indigo} />
          </Stack>
          {showWork && !anyWork && (
            <Typography variant="caption" color="text.secondary">
              Nothing running
            </Typography>
          )}
          {showWork && anyWork && (
            <Stack spacing={1}>
              <WorkGroup title="On GPU" rows={onGpu} empty="Nothing on the GPU" />
              <WorkGroup title="Not on GPU" rows={offGpu} empty="Nothing running off the GPU" />
            </Stack>
          )}
        </Stack>
      )}
    </Paper>
  );
}

function WorkGroup({ title, rows, empty }: { title: string; rows: Row[]; empty: string }) {
  return (
    <Box>
      <Typography
        variant="caption"
        sx={{ fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase", color: "text.secondary" }}
      >
        {title}
      </Typography>
      {rows.length === 0 ? (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.25 }}>
          {empty}
        </Typography>
      ) : (
        <Stack spacing={1} sx={{ mt: 0.5, maxHeight: 168, overflow: "auto", pr: 0.5 }}>
          {rows.map((row) => (
            <WorkRow key={row.id} row={row} />
          ))}
        </Stack>
      )}
    </Box>
  );
}
