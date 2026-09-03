"""The 60-hour intensity plot: axes, series, threshold bands and day ticks.

Apart from `display.py` because it changes for a different reason — the panel's
primitives change when the hardware does, this changes when the timeline does —
and because the two together were one file with more than one job.

Imported by bare module name, like every other module under pico/ — see
CLAUDE.md.
"""

from display import (
    EINK_BLACK,
    EINK_WHITE,
    draw_rect,
    draw_text,
    draw_vline,
    panel_dimensions,
)

from config import CONFIG

# Graph geometry, in pixels. The band at the bottom is left free for the day
# ticks; the dash pattern is the red percentile bands.
GRAPH_ORIGIN = (5, 60)
GRAPH_TICK_BAND = 9
GRAPH_DASH_LEN = 3
GRAPH_DASH_GAP = 5
# Day ticks: hours relative to now, and the label drawn under each.
GRAPH_DAY_TICKS = ((-48, "-2d"), (-24, "-1d"), (0, "now"))


class GraphAxes:
    """Where a value and an hour index land on the panel.

    Carries the six numbers the plotting used to close over — the value range,
    the box, the point count and the horizontal step — so the helpers below are
    module-level functions instead of definitions nested in `draw_graph`.
    """

    def __init__(self, epd, current_line, week_line):
        screen_w, screen_h = panel_dimensions(epd)
        self.base_x, self.base_y = GRAPH_ORIGIN
        self.width = max(10, screen_w - 10)
        self.height = max(10, min(90, screen_h - self.base_y - 5))
        self.plot_h = max(8, self.height - GRAPH_TICK_BAND)

        # Y-scale from min/max over last week + current timeline values.
        self.values = [
            v for v in current_line + week_line if isinstance(v, (int, float))
        ]
        self.low = min(self.values) if self.values else 0
        self.high = max(self.values) if self.values else 0

        graph_hours = CONFIG.timeline.back_hours_default + CONFIG.timeline.future_hours
        self.npts = min(graph_hours, max(len(current_line), len(week_line)))
        self.step_x = max(1, self.width - 2) / float(max(1, self.npts - 1))

    def norm(self, value):
        if value is None:
            return None
        if self.high == self.low:
            return 0.5
        return (value - self.low) / (self.high - self.low)

    def x_at(self, index):
        return self.base_x + 1 + int(round(index * self.step_x))

    def y_from_norm(self, normalized):
        normalized = min(1.0, max(0.0, normalized))
        return (
            self.base_y + (self.plot_h - 2) - int(round(normalized * (self.plot_h - 3)))
        )


def draw_series(frame, axes, values, dotted=False):
    for index in range(axes.npts - 1):
        a = values[index] if index < len(values) else None
        b = values[index + 1] if index + 1 < len(values) else None
        if a is None or b is None:
            continue
        x1, y1 = axes.x_at(index), axes.y_from_norm(a)
        x2, y2 = axes.x_at(index + 1), axes.y_from_norm(b)
        if not dotted:
            frame.line(x1, y1, x2, y2, EINK_BLACK)
            continue
        dx, dy = x2 - x1, y2 - y1
        steps = max(abs(dx), abs(dy))
        if steps <= 0:
            continue
        for step in range(0, steps + 1, 2):
            px = x1 + (dx * step) // steps
            py = y1 + (dy * step) // steps
            frame.pixel(px, py, EINK_BLACK)


def draw_dashed_hline(epd, x0, x1, y):
    x = int(x0)
    x1 = int(x1)
    y = int(y)
    while x <= x1:
        seg_end = min(x + GRAPH_DASH_LEN - 1, x1)
        seg_w = max(1, seg_end - x + 1)

        epd.black_frame.hline(x, y, seg_w, EINK_WHITE)
        epd.red_frame.hline(x, y, seg_w, EINK_BLACK)
        x = seg_end + GRAPH_DASH_GAP + 1


def value_at_percentile(sorted_values, percentile_value):
    if not sorted_values:
        return None
    percentile_value = min(1.0, max(0.0, float(percentile_value)))
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = percentile_value * (len(sorted_values) - 1)
    lo = int(pos)
    hi = lo + 1
    if hi >= len(sorted_values):
        return sorted_values[lo]
    frac = pos - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def draw_threshold_bands(epd, axes):
    """The red dashed lines at the percentile cutoffs, across the plot."""
    sorted_scale = sorted(axes.values)
    x0 = axes.base_x + 1
    x1 = axes.base_x + axes.width - 2
    for percentile_value in (
        CONFIG.thresholds.green_percentile_max,
        CONFIG.thresholds.yellow_percentile_max,
    ):
        value = value_at_percentile(sorted_scale, percentile_value)
        if value is None:
            continue
        draw_dashed_hline(epd, x0, x1, axes.y_from_norm(axes.norm(value)))


def draw_day_ticks(epd, axes):
    """The vertical at "now", then the -2d / -1d / now marks and their labels."""
    now_idx = CONFIG.timeline.back_hours_default
    if 0 <= now_idx < axes.npts:
        draw_vline(
            epd.black_frame,
            axes.x_at(now_idx),
            axes.base_y + 1,
            max(1, axes.plot_h - 1),
            color=EINK_BLACK,
        )

    tick_y0 = axes.base_y + axes.plot_h
    tick_y1 = axes.base_y + axes.height - 2
    for hour_offset, label in GRAPH_DAY_TICKS:
        idx = hour_offset + CONFIG.timeline.back_hours_default
        if idx < 0 or idx >= axes.npts:
            continue
        x = axes.x_at(idx)
        draw_vline(
            epd.black_frame, x, tick_y0, max(1, tick_y1 - tick_y0 + 1), color=EINK_BLACK
        )
        draw_text(
            epd.black_frame,
            max(axes.base_x + 1, x - 8),
            axes.base_y + axes.height - 8,
            label,
            color=EINK_BLACK,
        )


def draw_graph(epd, current_line, week_line):
    if not current_line and not week_line:
        draw_rect(epd.black_frame, 5, 55, 112, 80, color=0, fill=False)
        return

    axes = GraphAxes(epd, current_line, week_line)
    draw_rect(
        epd.black_frame,
        axes.base_x,
        axes.base_y,
        axes.width,
        axes.height,
        color=0,
        fill=False,
    )

    if not axes.values or axes.npts < 2:
        return

    # Current timeline: solid black. Previous-week timeline: dotted black.
    draw_series(epd.black_frame, axes, [axes.norm(v) for v in current_line])
    draw_series(epd.black_frame, axes, [axes.norm(v) for v in week_line], dotted=True)
    draw_threshold_bands(epd, axes)
    draw_day_ticks(epd, axes)
