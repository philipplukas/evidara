"""Shared plumbing for the experiment scripts: import path, plot style, CLI.

The palette is the validated categorical default (blue / orange / aqua / yellow / ...).
Its first three slots clear the all-pairs colour-vision gates, which is why the acoustic
dimensions -- the one place a figure routinely carries three simultaneous series -- use
slots 1-3 and always ship a legend plus distinct line styles, never colour alone.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from analysis.recording import results_dir  # noqa: E402

# validated categorical slots (light mode, surface #fcfcfb)
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#8a8984"
GRID = "#e3e2df"
LINESTYLES = ["-", "--", "-.", (0, (3, 1, 1, 1, 1, 1)), ":"]
MARKERS = ["o", "s", "^", "D", "v", "P"]

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "axes.titlesize": 10,
        "axes.titleweight": "bold",
        "axes.labelsize": 9,
        "axes.grid": True,
        "axes.axisbelow": True,  # grid behind the marks, never cutting through a bar
        "axes.spines.top": False,
        "axes.spines.right": False,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "text.color": INK,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "legend.frameon": False,
        "lines.linewidth": 1.8,
        "font.size": 9,
        "figure.dpi": 120,
        "pdf.fonttype": 42,
    }
)


def parse_args(description: str, **extra) -> argparse.Namespace:
    """Standard CLI. ``--quick`` shrinks every corpus so the whole suite runs in minutes."""
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--quick", action="store_true", help="small corpora for a fast smoke run")
    p.add_argument("--seed", type=int, default=0)
    for name, kwargs in extra.items():
        p.add_argument(f"--{name.replace('_', '-')}", **kwargs)
    return p.parse_args()


def n_sequences(args, full: int, quick: int) -> int:
    return quick if args.quick else full


def save(fig, name: str, run=None) -> Path:
    """Write a PDF (and a PNG alongside, for quick eyeballing) into ``results/``."""
    out = results_dir() / f"{name}.pdf"
    fig.savefig(out, bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    plt.close(fig)
    if run is not None:
        run.figure(out)
    print(f"  wrote {out.relative_to(ROOT)}")
    return out


def zero_line(ax) -> None:
    ax.axhline(0.0, color=MUTED, linewidth=0.9, zorder=1)


def label_last(ax, x, y, text: str, color: str, dx: float = 0.0, dy: float = 0.0) -> None:
    """Direct label at the end of a line -- identity without relying on colour alone."""
    ax.annotate(
        text,
        xy=(x[-1], y[-1]),
        xytext=(4 + dx, dy),
        textcoords="offset points",
        color=INK_2,
        fontsize=8,
        va="center",
        annotation_clip=False,
    )


def caption(fig, text: str) -> None:
    fig.text(0.0, -0.02, text, fontsize=7.5, color=MUTED, ha="left", va="top", wrap=True)


def ms(t: np.ndarray) -> np.ndarray:
    """Seconds -> milliseconds, for axes that read better in ms."""
    return np.asarray(t) * 1000.0
