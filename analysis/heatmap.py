"""Render an agreement heatmap for one neighbourhood, overlaid on a street basemap.

Colour = the share of that neighbourhood's hand-drawn boundaries that include
each point. Transparency scales with agreement, so streets stay readable under
the faint fringes and the agreed core reads solid.

Usage (matplotlib/contextily are pulled in on the fly, not project deps):

    cd analysis
    uv run --with matplotlib --with contextily heatmap.py "The Annex"

Writes analysis/out/heatmap-<slug>-<snapshot-date>.png
"""
import glob
import json
import os
import re
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import PowerNorm
from pyproj import Transformer
import contextily as cx

from names import assign_clusters
from geometry import parse_polygon, to_utm, coverage_grid
from analyze import (
    NAME_SIM_THRESHOLD, GRID_RES, MIN_AREA_M2, MAX_AREA_M2, DATA_DIR, OUT_DIR,
)

CRS = "EPSG:32617"


def load_cluster(target: str):
    snaps = sorted(glob.glob(os.path.join(DATA_DIR, "snapshot-*.json")))
    if not snaps:
        raise SystemExit("No snapshot found. Run: node analysis/fetch_snapshot.mjs")
    path = snaps[-1]
    date = os.path.basename(path).replace("snapshot-", "").replace(".json", "")
    subs = json.load(open(path))
    raw = [s.get("neighborhoodName", "") for s in subs]
    ids, labels = assign_clusters(raw, threshold=NAME_SIM_THRESHOLD)

    matches = [cid for cid, lbl in labels.items() if lbl.lower() == target.lower()]
    if not matches:
        near = sorted({lbl for lbl in labels.values() if target.lower() in lbl.lower()})
        raise SystemExit(
            f"No cluster labelled {target!r}."
            + (f" Did you mean: {', '.join(near[:8])}?" if near else "")
        )
    cid = matches[0]

    polys = []
    for s, c in zip(subs, ids):
        if c != cid:
            continue
        p = parse_polygon(s.get("polygonPoints", []))
        if p is None:
            continue
        u = to_utm(p)
        if MIN_AREA_M2 <= u.area <= MAX_AREA_M2:
            polys.append(u)
    return labels[cid], polys, date


def render(label: str, polys, date: str) -> str:
    n = len(polys)
    if n < 2:
        raise SystemExit(f"{label!r} has only {n} usable drawing(s) — nothing to compare.")

    gx, gy, counts, union = coverage_grid(polys, GRID_RES)
    minx, miny, maxx, maxy = union.bounds
    xs, ys = gx[0, :], gy[:, 0]
    frac = counts / n

    # Frame on the meaningfully-drawn area so streets stay legible; a few
    # outliers may extend beyond it.
    w = frac >= 0.08
    if not w.any():
        w = frac > 0
    pad = 500
    wx0, wx1 = gx[w].min() - pad, gx[w].max() + pad
    wy0, wy1 = gy[w].min() - pad, gy[w].max() + pad

    norm = PowerNorm(gamma=0.5, vmin=0, vmax=1)
    cmap = plt.cm.inferno
    rgba = cmap(norm(frac))
    alpha = np.clip(0.12 + 0.80 * frac, 0.0, 0.90)
    alpha[counts == 0] = 0.0
    rgba[..., 3] = alpha

    fig, ax = plt.subplots(figsize=(11, 9.5))
    ax.imshow(rgba, extent=[minx, maxx, miny, maxy], origin="lower",
              interpolation="bilinear", aspect="equal", zorder=3)
    cs = ax.contour(xs, ys, frac, levels=[0.5, 0.75],
                    colors=["#1f6feb", "#2ea043"], linewidths=1.8, zorder=4)
    ax.clabel(cs, fmt={0.5: "50% agree", 0.75: "75% agree"}, inline=True, fontsize=9)

    # most-agreed point
    imax = counts.argmax()
    ax.plot(gx.ravel()[imax], gy.ravel()[imax], "*", ms=20, color="white",
            mec="black", mew=1.0, zorder=6)
    ax.annotate(f"most-agreed spot\n{counts.max()} / {n} ({counts.max()/n:.0%})",
                (gx.ravel()[imax], gy.ravel()[imax]), textcoords="offset points",
                xytext=(12, 8), fontsize=9.5, weight="bold", color="white", zorder=7,
                path_effects=[pe.withStroke(linewidth=3, foreground="black")])

    ax.set_xlim(wx0, wx1); ax.set_ylim(wy0, wy1)
    ax.set_xticks([]); ax.set_yticks([])
    cx.add_basemap(ax, crs=CRS, source=cx.providers.CartoDB.Voyager, zoom=15,
                   zorder=0, attribution_size=6)

    ax.set_title(f"How much of the map gets called “{label}”?",
                 fontsize=16, weight="bold", loc="left", pad=22)
    ax.text(0, 1.015,
            f"n = {n} hand-drawn boundaries · colour = share of drawings including "
            f"each point · snapshot {date}",
            transform=ax.transAxes, fontsize=10, color="#555")

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    cbar = fig.colorbar(sm, ax=ax, fraction=0.046, pad=0.02)
    cbar.set_label("share of drawings including this area", fontsize=10)
    cbar.set_ticks([0, 0.1, 0.25, 0.5, 0.75, 1.0])
    cbar.set_ticklabels(["0", "10%", "25%", "50%", "75%", "100%"])

    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"heatmap-{slug}-{date}.png")
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
    return out


def main():
    if len(sys.argv) < 2:
        raise SystemExit('Usage: uv run --with matplotlib --with contextily '
                         'heatmap.py "<neighbourhood>"')
    label, polys, date = load_cluster(sys.argv[1])
    out = render(label, polys, date)
    print(f"{label}: {len(polys)} drawings → {out}")


if __name__ == "__main__":
    main()
