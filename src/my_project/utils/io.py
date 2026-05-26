import json
import pickle
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np

from my_project.config.locale_compat import normalize_lc_time

normalize_lc_time()

import pandas as pd

from my_project.utils.dataframe import merge_cols


# ファイルを読み込み、DataFrameとして返す
def read_file_to_df(
    file_path: Union[str, Path],
    *,
    sheet_name: Optional[str] = None,
    usecols: Optional[list] = None,
    header: Optional[Union[int, list[int]]] = 0,
    flatten_columns: bool = True,
    encoding: str = "utf-8-sig",
    index_col: Optional[Union[str, int]] = None,
    to_datetime: Optional[list[str]] = None,
    to_numeric: Optional[list[str]] = None,
    fillna0: bool = False, # floatまたはintの列のNaNを0で埋めるかどうか
    dropna: Optional[list[str]] = None, # dropnaの対象となる列
    drop_all: bool = True, # すべてNaNの行を削除するかそれとも一つでもNaNの行を削除するか
    drop_rule: Optional[int] = None, # None: dropnaのルール, 0: dropnaの代わりに0を含む行を削除するルール
) -> pd.DataFrame:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if sheet_name is None and suffix in {".xlsx", ".xls"}:
        sheet_name = 0  # デフォルトで最初のシートを読む

    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path, sheet_name=sheet_name, header=header, index_col=index_col)

    elif suffix == ".csv":
        df = pd.read_csv(path, header=header, encoding=encoding, index_col=index_col)

    elif suffix == ".parquet":
        df = pd.read_parquet(path)

    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    # header=[0,1] 等で MultiIndex になっている列をフラット化
    if flatten_columns and isinstance(df.columns, pd.MultiIndex):
        df.columns = [merge_cols(t) for t in df.columns]
    
    # 指定された列のみ抽出
    if usecols is not None:
        df = df[[c for c in usecols if c in df.columns]]
    
    # 指定された列を日付型に変換
    if to_datetime:
        for col in to_datetime:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
    # 指定された列を数値型に変換
    if to_numeric:
        for col in to_numeric:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

    # 指定された値でNaNを埋める
    if fillna0:
        float_cols = df.select_dtypes(include=["float", "int"]).columns
        df[float_cols] = df[float_cols].fillna(0)

    # 指定された列にNaNが含まれる行を削除
    if dropna:
        if drop_rule is None:
            if drop_all:
                df = df.dropna(subset=dropna, how="all")
            else:
                df = df.dropna(subset=dropna)
        elif drop_rule == 0:
            if drop_all:
                df = df[~(df[dropna] == 0).all(axis=1)]
            else:
                df = df[~(df[dropna] == 0).any(axis=1)]
    return df

# DFを指定したパスに保存する
def save_df_to_file(
    df: pd.DataFrame,
    file_path: Union[str , Path],
    index: bool = False,
) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        df.to_excel(path, index=index)
        print(f"Saved Excel file to {path}")
        return
    if suffix == ".csv":
        df.to_csv(path, index=index, encoding="utf-8-sig")
        print(f"Saved CSV file to {path}")
        return
    if suffix == ".parquet":
        df.to_parquet(path, engine='pyarrow', compression='snappy', index=index)
        print(f"Saved Parquet file to {path}")
        return
    raise ValueError(f"Unsupported file format: {suffix}")


# JSON保存用に変換
def to_jsonable(obj):
    if is_dataclass(obj):
        return to_jsonable(asdict(obj))

    if isinstance(obj, Enum):
        return obj.value

    if isinstance(obj, Path):
        return str(obj)

    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}

    if isinstance(obj, set):
        return sorted(to_jsonable(v) for v in obj)

    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]

    if isinstance(obj, (str, int, float, bool, np.integer, np.floating)) or obj is None:
        return str(obj)

    raise TypeError(f"Unsupported type for JSON: {type(obj)}")

# dictをJSONとして保存
def save_to_json(
    data: Any,
    file_path: Union[str , Path],
    indent: int = 2
) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    json_ready = to_jsonable(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(json_ready, f, ensure_ascii=False, indent=indent)
    print(f"Saved JSON file to {path}")

# dictをpickleとして保存
def save_to_pickle(
    data: Any,
    file_path: Union[str , Path],
) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"Saved pickle file to {path}")

# pickleファイルからデータを読み込む
def load_from_pickle(
    file_path: Union[str , Path],
) -> Any:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, "rb") as f:
        data = pickle.load(f)
    return data

def get_new_path(
    folder_path: Union[str , Path],
    name: str,
    file_type: str #.json, .pkl など
) -> str:
    return str(Path(folder_path) / f"{name}{file_type}" )

def save_json_and_pickle(
    data: Any,
    folder_path: Union[str , Path],
    name: str,
) -> None:
    save_to_json(
        data = data,
        file_path = get_new_path(folder_path, name, ".json"),
    )
    save_to_pickle(
        data = data,
        file_path = get_new_path(folder_path, name, ".pickle"),
    )
