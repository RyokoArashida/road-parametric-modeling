
from typing import Any, Sequence, Tuple

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


def get_single(obj: Any, context: str = ""):
    # DataFrame
    if isinstance(obj, pd.DataFrame):
        if obj.empty:
            raise ValueError(f"{context} に該当する行が存在しません")
        if len(obj) > 1:
            raise ValueError(f"{context} に該当する行が複数あります")
        return obj.iloc[0]

    # Series（すでに1行想定）
    if isinstance(obj, pd.Series):
        return obj

    # list / tuple
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes)):
        if len(obj) == 0:
            raise ValueError(f"{context} が空です")
        if len(obj) > 1:
            raise ValueError(f"{context} が複数あります")
        return obj[0]

    # その他
    raise TypeError(f"{context} の型が想定外: {type(obj)}")


