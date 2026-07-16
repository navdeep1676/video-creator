import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  Box,
  Chip,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import { mediaUrl } from "../api/client";

export type SlideListItem = {
  id: string;
  order_index: number;
  image_url: string | null;
  narration: { text: string; tts_status: string } | null;
};

type Props = {
  slides: SlideListItem[];
  selectedId: string | null;
  dirtySelected: boolean;
  draftPreview?: string | null;
  disabled?: boolean;
  onSelect: (id: string) => void;
  onReorder: (orderedIds: string[]) => void;
  onDelete: (id: string) => void;
  onMove: (id: string, direction: "up" | "down") => void;
};

function SortableSlideRow({
  slide,
  index,
  isActive,
  dirty,
  preview,
  disabled,
  isFirst,
  isLast,
  onSelect,
  onDelete,
  onMove,
}: {
  slide: SlideListItem;
  index: number;
  isActive: boolean;
  dirty: boolean;
  preview: string;
  disabled?: boolean;
  isFirst: boolean;
  isLast: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onMove: (dir: "up" | "down") => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: slide.id,
    disabled,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.7 : 1,
    zIndex: isDragging ? 2 : 1,
  };

  return (
    <Box
      ref={setNodeRef}
      style={style}
      onClick={onSelect}
      sx={{
        border: "1px solid",
        borderColor: isActive ? "primary.main" : "divider",
        borderRadius: 2,
        p: 1,
        cursor: "pointer",
        bgcolor: isActive ? "action.selected" : "background.paper",
        boxShadow: isDragging ? 4 : 0,
      }}
    >
      <Stack direction="row" spacing={0.5} alignItems="flex-start">
        <Tooltip title="Drag to reorder">
          <IconButton
            size="small"
            {...attributes}
            {...listeners}
            onClick={(e) => e.stopPropagation()}
            disabled={disabled}
            sx={{ cursor: disabled ? "default" : "grab", mt: 0.5 }}
            aria-label="Drag to reorder"
          >
            <DragIndicatorIcon fontSize="small" />
          </IconButton>
        </Tooltip>

        <Box
          component="img"
          src={mediaUrl(slide.image_url)}
          alt=""
          sx={{ width: 56, height: 40, objectFit: "cover", borderRadius: 1, bgcolor: "#eee", mt: 0.5 }}
        />

        <Box flex={1} minWidth={0}>
          <Typography variant="body2" fontWeight={600}>
            Slide {index + 1}
            {isActive && dirty ? " *" : ""}
          </Typography>
          <Typography variant="caption" color="text.secondary" noWrap display="block">
            {preview}
          </Typography>
          <Chip
            size="small"
            label={slide.narration?.tts_status || "missing"}
            color={
              slide.narration?.tts_status === "ready"
                ? "success"
                : slide.narration?.tts_status === "failed" ||
                    slide.narration?.tts_status === "cancelled"
                  ? "error"
                  : slide.narration?.tts_status === "processing" ||
                      slide.narration?.tts_status === "queued"
                    ? "warning"
                    : "default"
            }
            sx={{ height: 20, fontSize: 11, mt: 0.5 }}
          />
        </Box>

        <Stack spacing={0} onClick={(e) => e.stopPropagation()}>
          <Tooltip title="Move up">
            <span>
              <IconButton
                size="small"
                disabled={disabled || isFirst}
                onClick={() => onMove("up")}
                aria-label="Move slide up"
              >
                <KeyboardArrowUpIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="Move down">
            <span>
              <IconButton
                size="small"
                disabled={disabled || isLast}
                onClick={() => onMove("down")}
                aria-label="Move slide down"
              >
                <KeyboardArrowDownIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="Delete slide">
            <IconButton
              size="small"
              color="error"
              disabled={disabled}
              onClick={() => onDelete()}
              aria-label="Delete slide"
            >
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      </Stack>
    </Box>
  );
}

export default function SlideList({
  slides,
  selectedId,
  dirtySelected,
  draftPreview,
  disabled,
  onSelect,
  onReorder,
  onDelete,
  onMove,
}: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = slides.findIndex((s) => s.id === active.id);
    const newIndex = slides.findIndex((s) => s.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    const next = arrayMove(slides, oldIndex, newIndex).map((s) => s.id);
    onReorder(next);
  };

  if (slides.length === 0) {
    return (
      <Typography color="text.secondary" variant="body2">
        Upload PNG/JPG slides to begin.
      </Typography>
    );
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={slides.map((s) => s.id)} strategy={verticalListSortingStrategy}>
        <Stack spacing={1} maxHeight={560} overflow="auto">
          {slides.map((s, idx) => {
            const isActive = selectedId === s.id;
            const serverPreview = s.narration?.text?.trim()
              ? s.narration.text.trim().slice(0, 48) + (s.narration.text.length > 48 ? "…" : "")
              : "No narration";
            const preview =
              isActive && draftPreview != null
                ? (draftPreview || "No narration").slice(0, 48)
                : serverPreview;

            return (
              <SortableSlideRow
                key={s.id}
                slide={s}
                index={idx}
                isActive={isActive}
                dirty={isActive && dirtySelected}
                preview={preview}
                disabled={disabled}
                isFirst={idx === 0}
                isLast={idx === slides.length - 1}
                onSelect={() => onSelect(s.id)}
                onDelete={() => onDelete(s.id)}
                onMove={(dir) => onMove(s.id, dir)}
              />
            );
          })}
        </Stack>
      </SortableContext>
    </DndContext>
  );
}
