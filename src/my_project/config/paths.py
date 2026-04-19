from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

RESEARCH_ROOT = Path("G:\マイドライブ\研究\変更分析\BIM\御殿場JCT\エクセルファイル\Grasshopper用諸元")

INITIAL_DIR = RESEARCH_ROOT / "当初"
INITIAL_INPUT_DIR = INITIAL_DIR / "図面から入力"
INITIAL_OUTPUT_DIR = INITIAL_DIR / "出力"

FINAL_DIR = RESEARCH_ROOT / "最終"
FINAL_INPUT_DIR = FINAL_DIR / "図面から入力"
FINAL_OUTPUT_DIR = FINAL_DIR / "出力"
