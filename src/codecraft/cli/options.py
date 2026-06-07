from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer


CodecraftHomeOption = Annotated[
    Path,
    typer.Option(
        "--codecraft-home",
        help="Directory containing Codecraft runtime state.",
    ),
]
