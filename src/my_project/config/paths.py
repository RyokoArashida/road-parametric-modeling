import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _required_path(env_name: str) -> Path:
    value = os.getenv(env_name)
    if not value:
        raise RuntimeError(f"Required environment variable is not set: {env_name}")
    return Path(value)


def _path_from_env(env_name: str, default: Path) -> Path:
    value = os.getenv(env_name)
    return Path(value) if value else default


RESEARCH_ROOT = _required_path("ROAD_PARAMETRIC_RESEARCH_ROOT")

INITIAL_DIR = _path_from_env("ROAD_PARAMETRIC_INITIAL_DIR", RESEARCH_ROOT / "当初")
INITIAL_INPUT_DIR = _path_from_env(
    "ROAD_PARAMETRIC_INITIAL_INPUT_DIR",
    INITIAL_DIR / "図面から入力",
)
INITIAL_OUTPUT_DIR = _path_from_env(
    "ROAD_PARAMETRIC_INITIAL_OUTPUT_DIR",
    INITIAL_DIR / "出力",
)

FINAL_DIR = _path_from_env("ROAD_PARAMETRIC_FINAL_DIR", RESEARCH_ROOT / "最終")
FINAL_INPUT_DIR = _path_from_env(
    "ROAD_PARAMETRIC_FINAL_INPUT_DIR",
    FINAL_DIR / "図面から入力",
)
FINAL_OUTPUT_DIR = _path_from_env(
    "ROAD_PARAMETRIC_FINAL_OUTPUT_DIR",
    FINAL_DIR / "出力",
)
