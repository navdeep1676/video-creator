"""Map a Wan clip message onto the render percent band.

Scene clips occupy 10–40% of a render. Each clip owns an equal slice of that
band. Diffusion steps move inside the slice so the bar does not jump to the
end of the clip and then sit still. Stage text stays inside the 64-character
video_jobs.stage column.
"""

from __future__ import annotations

import re

_STEP = re.compile(r"step\s+(\d+)\s*/\s*(\d+)", re.IGNORECASE)
_STAGE_LIMIT = 64


def wan_clip_update(index: int, n_slides: int, message: str) -> tuple[int, str]:
    """Return (percent, stage) for one progress message from Wan."""
    count = max(int(n_slides), 1)
    slot = max(0, int(index))
    start = 10 + 30 * slot / count
    end = 10 + 30 * (slot + 1) / count
    span = max(end - start, 0.0)
    text = (message or "").strip()
    lower = text.lower()
    step = _STEP.search(lower)
    frac = 0.08
    label = "working"
    if "cached" in lower:
        frac = 1.0
        label = "cached"
    elif step:
        done = int(step.group(1))
        total = max(int(step.group(2)), 1)
        done = min(max(done, 0), total)
        frac = 0.08 + 0.84 * (done / total)
        label = f"step {done}/{total}"
    elif "export" in lower:
        frac = 0.97
        label = "exporting"
    elif "load" in lower:
        frac = 0.04
        label = "loading model"
    elif "sampling" in lower:
        frac = 0.08
        label = "sampling"
    elif "generat" in lower or "start" in lower:
        frac = 0.02
        label = "starting"
    elif text:
        label = text
    percent = int(round(start + span * frac))
    percent = max(0, min(99, percent))
    stage = f"wan {slot + 1}/{count} {label}"
    return percent, stage[:_STAGE_LIMIT]
