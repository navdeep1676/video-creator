import { useState } from "react";
import { Box, Button, Chip, IconButton, Stack, Tab, Tabs, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DownloadIcon from "@mui/icons-material/Download";

export type StoryCharacterView = {
  id: string;
  name: string;
  age: string | null;
  appearance: string;
  clothing: string;
  personality: string;
  style: string;
  seed: number;
};

export type StoryLocationView = {
  id: string;
  name: string;
  description: string;
  lighting: string;
  mood: string;
};

export type StorySceneView = {
  id: string;
  index: number;
  beat: string;
  narration: string;
  dialogue: string;
  duration: number;
  start_time: number;
  end_time: number;
  generation_mode: string;
  status: string;
  image_prompt: string;
  video_prompt: string;
  camera_motion: string;
  transition: string;
  sfx: string[];
  characters: string[];
  location: string;
};

export type StoryView = {
  title: string;
  hook: string;
  body: string;
  lyrics: string | null;
  kids_format: string | null;
  music_prompt: string;
  sfx_notes: string;
  plan: Record<string, unknown>;
};

const BEAT_COLOR: Record<string, "default" | "primary" | "secondary" | "error" | "warning" | "success" | "info"> = {
  hook: "primary",
  setup: "info",
  tension: "warning",
  escalation: "warning",
  reveal: "secondary",
  climax: "error",
  ending: "success",
};

function formatSeconds(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? `${rounded.toFixed(0)}s` : `${rounded.toFixed(1)}s`;
}

function formatClock(value: number): string {
  const total = Math.max(0, Math.round(value));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function fileSlug(title: string): string {
  const slug = title
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "");
  return slug.slice(0, 80) || "story";
}

function jsonText(plan: Record<string, unknown> | null | undefined): string {
  return JSON.stringify(plan ?? {}, null, 2);
}

function PromptBlock({ label, text }: { label: string; text: string }) {
  if (!text.trim()) return null;
  return (
    <Box sx={{ bgcolor: "rgba(109,40,217,0.06)", borderRadius: 2, p: 1.5 }}>
      <Typography variant="caption" color="text.secondary" fontWeight={700} display="block" sx={{ mb: 0.5 }}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
        {text}
      </Typography>
    </Box>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  if (!value.trim()) return null;
  return (
    <Typography variant="body2" color="text.secondary">
      <Box component="span" sx={{ fontWeight: 700, color: "text.primary" }}>
        {label}.{" "}
      </Box>
      {value}
    </Typography>
  );
}

export default function StoryReview({
  story,
  scenes,
  characters,
  locations,
  onClose,
}: {
  story: StoryView;
  scenes: StorySceneView[];
  characters: StoryCharacterView[];
  locations: StoryLocationView[];
  onClose?: () => void;
}) {
  const [tab, setTab] = useState("story");
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const text = jsonText(story.plan ?? {});
  const videoCount = scenes.filter((scene) => scene.generation_mode === "video").length;
  const totalDuration = scenes.reduce((sum, scene) => sum + (scene.duration || 0), 0);

  const copyJson = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
    window.setTimeout(() => setCopyState("idle"), 2000);
  };

  const downloadJson = () => {
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${fileSlug(story.title)}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const copyLabel = copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy JSON";

  return (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column", bgcolor: "background.paper" }}>
      <Box sx={{ px: 2, pt: 1.5, borderBottom: 1, borderColor: "divider" }}>
        <Stack direction="row" spacing={1} alignItems="flex-start">
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="h6" sx={{ overflowWrap: "anywhere" }}>
              {story.title}
            </Typography>
          </Box>
          {onClose && (
            <IconButton aria-label="Close story review" onClick={onClose} size="small">
              <CloseIcon />
            </IconButton>
          )}
        </Stack>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mt: 1 }}>
          <Chip size="small" color="primary" label={`${scenes.length} scenes`} />
          <Chip size="small" label={`${videoCount} video · ${scenes.length - videoCount} image`} />
          {totalDuration > 0 && <Chip size="small" label={formatSeconds(totalDuration)} />}
          {story.kids_format && <Chip size="small" label={story.kids_format.replace(/_/g, " ")} />}
        </Stack>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mt: 1.25 }}>
          <Button size="small" variant="outlined" startIcon={<ContentCopyIcon />} onClick={() => void copyJson()}>
            {copyLabel}
          </Button>
          <Button size="small" variant="outlined" startIcon={<DownloadIcon />} onClick={downloadJson}>
            Download JSON
          </Button>
        </Stack>
        <Tabs
          value={tab}
          onChange={(_event, value: string) => setTab(value)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ mt: 1 }}
        >
          <Tab value="story" label="Story" />
          <Tab value="scenes" label={`Scenes ${scenes.length}`} />
          <Tab value="cast" label={`Cast ${characters.length}`} />
          <Tab value="places" label={`Places ${locations.length}`} />
          <Tab value="json" label="JSON" />
        </Tabs>
      </Box>
      <Box sx={{ flex: 1, overflow: "auto", p: 2 }}>
        {tab === "story" && (
          <Stack spacing={2}>
            {story.hook && (
              <Box sx={{ borderLeft: "3px solid", borderColor: "primary.main", pl: 2 }}>
                <Typography variant="body1" fontWeight={600} sx={{ whiteSpace: "pre-wrap" }}>
                  {story.hook}
                </Typography>
              </Box>
            )}
            {story.body && (
              <Typography variant="body1" sx={{ whiteSpace: "pre-wrap" }}>
                {story.body}
              </Typography>
            )}
            {story.lyrics && (
              <Box sx={{ bgcolor: "rgba(109,40,217,0.06)", borderRadius: 2, p: 1.5 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={700} display="block" sx={{ mb: 0.5 }}>
                  Lyrics
                </Typography>
                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                  {story.lyrics}
                </Typography>
              </Box>
            )}
            <PromptBlock label="Music prompt" text={story.music_prompt} />
            <PromptBlock label="Sound notes" text={story.sfx_notes} />
          </Stack>
        )}

        {tab === "cast" && (
          <Stack spacing={1.5}>
            {characters.length === 0 && (
                <Typography variant="body2" color="text.secondary">
                  This plan has no characters.
                </Typography>
              )}
              {characters.map((character) => (
                <Box key={character.id} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 2, p: 1.5 }}>
                  <Stack direction="row" spacing={1} alignItems="baseline" flexWrap="wrap" useFlexGap>
                    <Typography variant="subtitle1">{character.name}</Typography>
                    {character.age && (
                      <Typography variant="caption" color="text.secondary">
                        {character.age}
                      </Typography>
                    )}
                    <Typography variant="caption" color="text.secondary">
                      Seed {character.seed}
                    </Typography>
                  </Stack>
                  <Stack spacing={0.5} sx={{ mt: 0.75 }}>
                    <Fact label="Look" value={character.appearance} />
                    <Fact label="Clothes" value={character.clothing} />
                    <Fact label="Personality" value={character.personality} />
                    <Fact label="Style" value={character.style} />
                  </Stack>
                </Box>
            ))}
          </Stack>
        )}

        {tab === "places" && (
          <Stack spacing={1.5}>
            {locations.length === 0 && (
                <Typography variant="body2" color="text.secondary">
                  This plan has no locations.
                </Typography>
              )}
              {locations.map((location) => (
                <Box key={location.id} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 2, p: 1.5 }}>
                  <Typography variant="subtitle1">{location.name}</Typography>
                  <Stack spacing={0.5} sx={{ mt: 0.75 }}>
                    <Fact label="Place" value={location.description} />
                    <Fact label="Light" value={location.lighting} />
                    <Fact label="Mood" value={location.mood} />
                  </Stack>
                </Box>
            ))}
          </Stack>
        )}

        {tab === "scenes" && (
          <Stack spacing={1.5}>
            {scenes.length === 0 && (
              <Typography variant="body2" color="text.secondary">
                This plan has no scenes.
              </Typography>
            )}
            {scenes.map((scene) => (
              <Box key={scene.id} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 2, p: { xs: 1.5, sm: 2 } }}>
                <Stack spacing={1.25}>
                  <Stack direction="row" spacing={1.25} alignItems="flex-start">
                    <Box
                      sx={{
                        width: 36,
                        height: 36,
                        borderRadius: "50%",
                        bgcolor: "primary.main",
                        color: "primary.contrastText",
                        display: "grid",
                        placeItems: "center",
                        fontWeight: 800,
                        flexShrink: 0,
                      }}
                    >
                      {scene.index + 1}
                    </Box>
                    <Stack spacing={0.75} sx={{ minWidth: 0, flex: 1 }}>
                      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
                        {scene.beat && (
                          <Chip size="small" color={BEAT_COLOR[scene.beat] ?? "default"} label={scene.beat} />
                        )}
                        <Chip
                          size="small"
                          variant="outlined"
                          color={scene.generation_mode === "video" ? "secondary" : "default"}
                          label={scene.generation_mode === "video" ? "Video" : "Image"}
                        />
                        <Chip size="small" variant="outlined" label={formatSeconds(scene.duration)} />
                        {(scene.start_time > 0 || scene.end_time > 0) && (
                          <Typography variant="caption" color="text.secondary">
                            {formatClock(scene.start_time)}–{formatClock(scene.end_time)}
                          </Typography>
                        )}
                        {scene.status && scene.status !== "pending" && (
                          <Chip size="small" variant="outlined" label={scene.status} />
                        )}
                      </Stack>
                      <Typography variant="body1" sx={{ whiteSpace: "pre-wrap" }}>
                        {scene.narration}
                      </Typography>
                    </Stack>
                  </Stack>
                  {scene.dialogue.trim() && <Fact label="Dialogue" value={scene.dialogue} />}
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                    {scene.location && <Chip size="small" variant="outlined" label={scene.location} />}
                    {scene.characters.map((name, nameIndex) => (
                      <Chip key={`${name}-${nameIndex}`} size="small" variant="outlined" label={name} />
                    ))}
                    {scene.camera_motion && <Chip size="small" variant="outlined" label={scene.camera_motion} />}
                    {scene.transition && <Chip size="small" variant="outlined" label={scene.transition} />}
                    {scene.sfx.map((cue, cueIndex) => (
                      <Chip key={`${cue}-${cueIndex}`} size="small" label={cue} />
                    ))}
                  </Stack>
                  <PromptBlock label="Image prompt" text={scene.image_prompt} />
                  <PromptBlock label="Video prompt" text={scene.video_prompt} />
                </Stack>
              </Box>
            ))}
          </Stack>
        )}

        {tab === "json" && (
          <Stack spacing={1}>
            <Typography variant="caption" color="text.secondary">
              {text.length.toLocaleString()} characters
            </Typography>
            <Box
              component="pre"
              sx={{
                m: 0,
                p: 2,
                overflow: "auto",
                borderRadius: 2,
                bgcolor: "#0B1020",
                color: "#E2E8F0",
                fontSize: 12.5,
                lineHeight: 1.55,
                fontFamily: 'ui-monospace, "Noto Sans Devanagari", SFMono-Regular, Menlo, monospace',
                whiteSpace: "pre-wrap",
                overflowWrap: "anywhere",
              }}
            >
              {text}
            </Box>
          </Stack>
        )}
      </Box>
    </Box>
  );
}

