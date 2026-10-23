"""Themed matplotlib bar charts. Kept in their own module so matplotlib loads only when a chart is shown."""
from __future__ import annotations

import matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QSizePolicy

from ..core.trace import Chart
from .theme import theme


class ChartView(FigureCanvasQTAgg):
    """A themed matplotlib bar chart for core.trace.Chart specs."""

    def __init__(self, parent=None, height: float = 2.6):
        self.fig = Figure(figsize=(6, height), layout="constrained")
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(int(height * 55))
        self._chart: Chart | None = None
        theme().changed.connect(self._retheme)  # bound method: auto-disconnected when the chart is deleted

    def _retheme(self) -> None:
        self.show_chart(self._chart)

    def show_chart(self, chart: Chart | None) -> None:
        self._chart = chart
        ui = theme().ui
        matplotlib.rcParams["font.family"] = [theme().ui_font, "DejaVu Sans"]
        self.fig.clear()
        self.fig.set_facecolor(ui["card"])
        if chart is None:
            self.draw_idle()
            return
        ax = self.fig.add_subplot(111)
        ax.set_facecolor(ui["card"])
        names = list(chart.series)
        k = len(names)
        width = 0.8 / max(1, k)
        xs = range(len(chart.labels))
        for s, name in enumerate(names):
            vals = chart.series[name]
            color = ui["series"][s % len(ui["series"])]
            bars = ax.bar([x - 0.4 + width * (s + 0.5) for x in xs], vals, width * 0.92, label=name, color=color,
                          alpha=1.0 if s == 0 else 0.8, zorder=3)
            for h in chart.highlight:
                if 0 <= h < len(bars) and s == 0:
                    bars[h].set_color(ui["result"])
        for i, (name, v) in enumerate(chart.refs.items()):
            ax.axhline(v, ls="--", lw=1.2, color=ui["series"][(i + 1) % 4], label=f"{name} ({v:.3f})", zorder=4)
        ax.set_xticks(list(xs))
        ax.set_xticklabels(chart.labels, fontsize=8 if len(chart.labels) > 26 else 9,
                           rotation=90 if max((len(lb) for lb in chart.labels), default=0) > 3 else 0)
        ax.set_title(chart.title, color=ui["text"], fontsize=10.5, loc="left")
        ax.set_ylabel(chart.ylabel, color=ui["muted"])
        ax.tick_params(colors=ui["muted"], length=0)
        ax.grid(axis="y", color=ui["border"], lw=0.8, zorder=0)
        for sp in ax.spines.values():
            sp.set_visible(False)
        if k > 1 or chart.refs:
            leg = ax.legend(fontsize=8.5, frameon=False)
            for t in leg.get_texts():
                t.set_color(ui["text"])
        self.draw_idle()
