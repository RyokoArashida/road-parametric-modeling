from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

from my_project.config.schemas.superstructure_schemas import (
    CrossGirderOffsetInfo,
)
from my_project.config.util_schemas import (
    Frame2D,
    LocalOffset,
    MonoSlope,
    Point2D,
    Point3D,
)


@dataclass(frozen=True)
class MainGirder