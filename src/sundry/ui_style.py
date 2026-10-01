"""Shared terminal identity and semantic palettes."""

from __future__ import annotations

import os
from typing import TypeVar

from rich.text import Text
from textual.app import App
from textual.theme import Theme

T = TypeVar("T")

PALETTES = [
    Theme(
        name="sundry-neon",
        primary="#b899ff",
        secondary="#63d9ec",
        accent="#ffc078",
        success="#91dfad",
        warning="#ffd280",
        error="#ff8096",
        foreground="#e3e9fa",
        background="#101322",
        surface="#171c30",
        panel="#222a43",
    ),
    Theme(
        name="sundry-ember",
        primary="#ffb47b",
        secondary="#d3a3ef",
        accent="#88ddd0",
        success="#b3dc97",
        warning="#f3d089",
        error="#ff8790",
        foreground="#f2e5dd",
        background="#1b161c",
        surface="#271f29",
        panel="#382a35",
    ),
    Theme(
        name="sundry-forest",
        primary="#98d5b1",
        secondary="#8dcddd",
        accent="#e4c896",
        success="#a3dc8a",
        warning="#e9ce81",
        error="#f29b96",
        foreground="#e0ebe4",
        background="#111d1b",
        surface="#192a27",
        panel="#233a34",
    ),
]

LOGO = r"""  ____  _   _ _   _ ____  ______   __
 / ___|| | | | \ | |  _ \|  _ \ \ / /
 \___ \| | | |  \| | | | | |_) \ V /
  ___) | |_| | |\  | |_| |  _ < | |
 |____/ \___/|_| \_|____/|_| \_\|_|"""


def banner(primary: str, secondary: str, compact: bool = False) -> Text:
    text = Text("S U N D R Y" if compact else LOGO, style=f"bold {primary}")
    text.append("\n  RESEARCH  /  CURATE  /  EVALUATE", style=secondary)
    return text


class SundryApp(App[T]):
    """Interactive colors are explicit; the plain CLI still honors NO_COLOR."""

    def __init__(self, *, color_enabled: bool = True) -> None:
        previous = os.environ.pop("NO_COLOR", None)
        if not color_enabled:
            os.environ["NO_COLOR"] = "1"
        try:
            super().__init__()
        finally:
            os.environ.pop("NO_COLOR", None)
            if previous is not None:
                os.environ["NO_COLOR"] = previous
        for theme in PALETTES:
            self.register_theme(theme)
        self.theme = "sundry-neon"
