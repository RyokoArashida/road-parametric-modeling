# ruff: noqa: E402

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

import pandas as pd


# 複数行にまたがる列名を1行にまとめる
def merge_cols(col_tuple) -> str:
    def is_na_like(x) -> bool:
        return pd.isna(x) or str(x).strip() == "" or "Unnamed" in str(x)

    parts = [str(x).strip() for x in col_tuple if not is_na_like(x)]
    return "_".join(parts)


def explode_multi_category(
    df: pd.DataFrame,
    col: str,
    sep: str = r'\s*,\s*', # デフォルトはカンマ区切り（カンマの前後に空白があってもなくても区切りとみなす）
    dropna: bool = True,
    reset_index: bool = True
) -> pd.DataFrame:
    """
    指定列に複数カテゴリ（区切り文字区切り）が含まれる場合、
    1カテゴリ = 1行になるように DataFrame を展開する。
    """
    tmp = df.copy()
    tmp[col] = (
        tmp[col]
        .astype("string")
        .str.split(sep)
    )
    tmp = tmp.explode(col)
    
    if dropna:
        tmp = tmp[tmp[col].notna()]
    
    if reset_index:
        tmp = tmp.reset_index(drop=True)
    
    return tmp


def to_dict_recursive(obj: Any) -> Any:
    """
    すべてのclassインスタンスをdictに変換する。
    dict / list / tuple は中も再帰的に処理。
    それ以外はそのまま返す。
    """
    # dict
    if isinstance(obj, Mapping):
        return {k: to_dict_recursive(v) for k, v in obj.items()}

    # dataclass
    if is_dataclass(obj) and not isinstance(obj, type):
        return to_dict_recursive(asdict(obj))

    # list / tuple / set
    if isinstance(obj, (list, tuple, set)):
        return [to_dict_recursive(v) for v in obj]

    # 通常class（__dict__を持つもの）
    if hasattr(obj, "__dict__"):
        return {
            k: to_dict_recursive(v)
            for k, v in vars(obj).items()
            if not callable(v)
        }

    # その他（プリミティブやRhinoオブジェクトなど）
    return obj


def flatten_dict(
    d: Mapping,
    parent_key: str = "",
    sep: str = "_",
) -> dict[str, Any]:
    """
    dictのみを対象にフラット化
    """
    result: dict[str, Any] = {}

    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)

        if isinstance(v, Mapping):
            result.update(flatten_dict(v, new_key, sep))
        else:
            result[new_key] = v

    return result


def flatten_any(obj: Any, sep: str = "_") -> dict[str, Any]:
    """
    ユーザー用インターフェース：
    class → dict → flatten を一気にやる
    """
    dict_obj = to_dict_recursive(obj)

    if not isinstance(dict_obj, Mapping):
        return {"value": dict_obj}

    return flatten_dict(dict_obj, sep=sep)

def get_single_value(series: pd.Series, context: str = ""):
    if series.empty:
        raise ValueError(f"{context} に該当する値が存在しません")
    if len(series) > 1:
        raise ValueError(f"{context} に該当する値が複数あります")
    return series.iloc[0]
