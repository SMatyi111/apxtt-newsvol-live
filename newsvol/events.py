"""Scheduled-event flags. File model/events_utc.csv: event,utc_time (YYYY-MM-DD HH:MM, release minute in UTC).
Event hour = the hour that contains the release minute; the hour after gets its own dummy (ev_<k>_post)."""
import pandas as pd

from .model import EVS


def read_events(path):
    ev = pd.read_csv(path, comment="#")
    ev["utc_time"] = pd.to_datetime(ev["utc_time"])
    ev = ev[ev["event"].isin(EVS)]
    return {k: set(ev.loc[ev["event"] == k, "utc_time"].dt.floor("h")) for k in EVS}


def flags_for(events, target_utc):
    """target_utc: naive UTC hour start -> {ev_k: 0/1, ev_k_post: 0/1}."""
    t = pd.Timestamp(target_utc)
    prev = t - pd.Timedelta(hours=1)
    out = {}
    for k in EVS:
        out[f"ev_{k}"] = 1 if t in events[k] else 0
        out[f"ev_{k}_post"] = 1 if prev in events[k] else 0
    return out
