
from typing import Tuple

import pandas as pd

from my_project.config.util_schemas import (
    Point2D,
)


def m_coord_to_mm(coord: float) -> float:
    return round(coord * 1000, 1) # 有効数字がmの時に.4桁だったから。

def get_coord_data(
    coord_df: pd.DataFrame,
    pier_name: str,
    point_name: str,
) -> Point2D:
    x_row = coord_df[(coord_df["橋脚名"] == pier_name) & (coord_df["XY"] == "Y")]
    y_row = coord_df[(coord_df["橋脚名"] == pier_name) & (coord_df["XY"] == "X")]
    point_x = m_coord_to_mm(x_row[point_name].values[0])
    point_y = m_coord_to_mm(y_row[point_name].values[0])
    return Point2D(x=point_x, y=point_y)

def get_four_corners(coord_df: pd.DataFrame, pier_name: str, corner_names:Tuple[str, str, str, str]) -> Tuple[Point2D, Point2D, Point2D, Point2D]:
    return tuple(get_coord_data(coord_df, pier_name, corner_name) for corner_name in corner_names)




