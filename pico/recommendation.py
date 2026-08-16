import time
from i18n import t


from utils import floor_hour_epoch, fmt_hhmm_local, iso_z_to_epoch, percentile

from config import CONFIG


def compute_recommendation(current_carbon_intensity, overlay_history, now_epoch):
    values = [
        float(item.get("carbonIntensity"))
        for item in overlay_history
        if isinstance(item.get("carbonIntensity"), (int, float))
    ]
    if len(values) < 24:
        return {
            "verdict": "OK",
            "reason": "Collecting baseline",
            "next_best": "recheck",
            "wait_hours": None,
        }

    values.sort()
    current_percentile = percentile(values, current_carbon_intensity)
    wait_hours, next_best = _compute_next_best(overlay_history, now_epoch)

    if current_percentile <= CONFIG.thresholds.green_percentile_max:
        return {
            "verdict": t("verdict.run_now"),
            "reason": t("reason.cleaner"),
            "next_best": t("label.now"),
            "wait_hours": 0,
        }
    if current_percentile <= CONFIG.thresholds.yellow_percentile_max:
        return {
            "verdict": t("verdict.ok"),
            "reason": t("reason.average"),
            "next_best": next_best,
            "wait_hours": wait_hours or 0,
        }
    return {
        "verdict": t("verdict.wait"),
        "reason": t("reason.dirtier"),
        "next_best": next_best,
        "wait_hours": wait_hours,
    }


def _compute_next_best(overlay_history, now_epoch):
    best = None
    horizon_epoch = now_epoch + (CONFIG.timeline.future_hours * 3600)
    for point in overlay_history:
        ts = point.get("datetime")
        ci = point.get("carbonIntensity")
        if not ts or not isinstance(ci, (int, float)):
            continue
        point_epoch = iso_z_to_epoch(ts)
        if point_epoch is None:
            continue
        shifted_epoch = point_epoch + (7 * 24 * 3600)
        if not (now_epoch < shifted_epoch <= horizon_epoch):
            continue
        if best is None or ci < best[1]:
            best = (shifted_epoch, ci)

    if best is None:
        return None, "recheck"

    wait_hours = int(round(max(0, (best[0] - now_epoch)) / 3600))
    return wait_hours, "in %dh (%s)" % (wait_hours, fmt_hhmm_local(best[0]))


def recommend_from_week(current_ci, week_history_points, *_, **__):
    now_epoch = floor_hour_epoch(int(time.time()))
    return compute_recommendation(current_ci, week_history_points or [], now_epoch)
