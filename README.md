English follows Japanese.

# Road Parametric Modeling

## 日本語

## このリポジトリの目的

このリポジトリは、道路橋の上部工・下部工に関する Excel 諸元データを読み込み、Rhino / Grasshopper で利用するための中間データと形状生成用データを作成するための Python スクリプト群です。

主な流れは、Excel 入力データを前処理して JSON / pickle 形式の中間データを作成し、その中間データを Grasshopper / Rhino 側のスクリプトで読み込んで、Brep や Surface などの Rhino ジオメトリを生成する、というものです。

このリポジトリは、当初モデルと最終モデルを比較する目的で作成されています。そのため、多くのスクリプトには `main("initial")` と `main("final")` の分岐があります。この引数は主に入力・出力フォルダを切り替えるためのものです。

## 全体のフォルダ構成

```text
road-parametric-modeling/
├── all.gh
├── pyproject.toml
├── scripts/
│   └── preprocess/
│       ├── abutment.py
│       ├── barrier.py
│       ├── cross_girder.py
│       ├── I_box_joint.py
│       ├── main_girder.py
│       ├── pier.py
│       ├── shoe.py
│       ├── slab.py
│       ├── superstructure_common.py
│       └── superstructure_coords.py
├── scripts_gh/
│   ├── bake.py
│   ├── substructure/
│   │   ├── const_abut.py
│   │   ├── const_column.py
│   │   ├── const_foundation.py
│   │   ├── const_piertop.py
│   │   └── const_shoe.py
│   └── superstructure/
│       ├── const_barriers.py
│       ├── const_cross_girder.py
│       ├── const_I_box_joint.py
│       ├── const_main_girder.py
│       └── const_slab.py
└── src/
    └── my_project/
        ├── config/
        │   ├── file_names.py
        │   ├── paths.py
        │   ├── util_schemas.py
        │   └── schemas/
        └── utils/
            ├── bake.py
            ├── coordinates.py
            ├── dataframe.py
            ├── geometry/
            ├── geometry_gh/
            ├── io.py
            └── proprocess.py
```

- `all.gh`: Grasshopper ファイルです。`scripts_gh/` 内のスクリプトを実行し、実際に bake するために使います。
- `scripts/preprocess/`: Excel 入力を読み込み、JSON / pickle の中間データへ変換する前処理スクリプト群です。
- `scripts_gh/`: Rhino / Grasshopper 環境で実行する形状生成スクリプト群です。
- `scripts_gh/superstructure/`: 床版、主桁、横桁、壁高欄、鈑桁・箱桁接続部など、上部工の形状生成を扱います。
- `scripts_gh/substructure/`: 橋脚、橋台、柱、基礎、支承など、下部工および支承まわりの形状生成を扱います。
- `src/my_project/config/`: 入出力パス、ファイル名定数、dataclass スキーマを定義します。
- `src/my_project/utils/`: ファイル入出力、座標変換、DataFrame 変換、幾何計算、Grasshopper 用の補助処理を提供します。

## 主なスクリプトの役割

### 前処理スクリプト

前処理スクリプトは主に `scripts/preprocess/` にあります。直接実行した場合は、多くのスクリプトで `main("initial")` が呼ばれます。`initial` / `final` は、当初データと最終データの入力・出力フォルダを切り替えるために使います。

- `superstructure_coords.py`: 上部工座標を読み込み、ローカル座標をワールド座標へ変換し、変換済み座標を出力します。
- `superstructure_common.py`: 変換済み上部工座標を読み込み、上部工の共通座標情報を出力します。
- `slab.py`: 床版に関する入力データを作成します。
- `main_girder.py`: 主桁に関する入力データを作成します。
- `cross_girder.py`: 横梁、対傾構、横桁に関する入力データと参照点データを作成します。
- `barrier.py`: 壁高欄および中央壁高欄に関する入力データを作成します。
- `I_box_joint.py`: 鈑桁・箱桁接続部に関する入力データを作成します。
- `pier.py`: 橋脚の個別・共通入力データを作成します。
- `abutment.py`: 橋台の個別・共通入力データを作成します。
- `shoe.py`: 支承および変位防止構造に関する入力データを作成します。

### Grasshopper / Rhino 用スクリプト

`scripts_gh/` 以下のスクリプトは、前処理で作成された pickle を読み込み、Rhino.Geometry のジオメトリを作成します。多くのスクリプトは Grasshopper で bake するための `bake_keys` と `bake_objs` を返します。

- `scripts_gh/superstructure/const_slab.py`: 床版形状、主桁上フランジ点、床版下面点、床版上面端部点などを生成します。
- `scripts_gh/superstructure/const_main_girder.py`: 主桁の点群および主桁 Brep を生成します。
- `scripts_gh/superstructure/const_cross_girder.py`: 横梁、対傾構、横桁の Brep を生成します。
- `scripts_gh/superstructure/const_barriers.py`: 壁高欄、中央壁高欄、ノーズ部などを生成します。
- `scripts_gh/superstructure/const_I_box_joint.py`: 鈑桁・箱桁接続部を生成します。
- `scripts_gh/substructure/const_column.py`: 橋脚柱と橋脚天端点を生成します。
- `scripts_gh/substructure/const_piertop.py`: 橋脚天端の面や梁部を生成します。
- `scripts_gh/substructure/const_foundation.py`: フーチング、杭、ケーソン基礎を生成します。
- `scripts_gh/substructure/const_abut.py`: 橋台の梁座、胸壁、翼壁、床版受け、壁高欄基準点などを生成します。
- `scripts_gh/substructure/const_shoe.py`: 支承および変位防止構造を生成します。
- `scripts_gh/bake.py`: Grasshopper から Rhino ドキュメントへ Brep を bake する補助スクリプトです。

## 入力データの説明

入力 Excel データは GitHub には含めていません。サンプルデータが必要な場合は、著者に連絡すれば提供可能です。

## 実行手順

### 1. Python 環境を用意する

Python 3.9 以上が必要です。

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

`pyproject.toml` には、通常の Python 環境で必要になる `pandas`, `numpy`, `openpyxl`, `matplotlib`, `python-dotenv`, `pyproj`, `pyarrow` が定義されています。Rhino / Grasshopper 関連 API は通常の pip パッケージではなく、Rhino / Grasshopper の Python 実行環境で利用する前提です。

### 2. 入出力パスを設定する

入出力パスは `src/my_project/config/paths.py` で定義されています。個人環境に依存するパスは `.env` に記述します。

```powershell
Copy-Item .env.example .env
```

`.env` の `ROAD_PARAMETRIC_RESEARCH_ROOT` に、当初・最終フォルダを含む作業ディレクトリを設定してください。

必要に応じて、`ROAD_PARAMETRIC_INITIAL_DIR`, `ROAD_PARAMETRIC_INITIAL_INPUT_DIR`, `ROAD_PARAMETRIC_INITIAL_OUTPUT_DIR`, `ROAD_PARAMETRIC_FINAL_DIR`, `ROAD_PARAMETRIC_FINAL_INPUT_DIR`, `ROAD_PARAMETRIC_FINAL_OUTPUT_DIR` で各フォルダを個別に上書きできます。

### 3. Excel 入力データを配置する

`.env` で設定した入力フォルダに Excel 入力データを配置します。

このリポジトリには入力 Excel データは含まれていません。サンプルデータが必要な場合は著者に連絡してください。

### 4. 前処理を実行する

各スクリプトはデフォルトで `main("initial")` を実行します。`final` 側を処理する場合は、対象スクリプトまたは Grasshopper 側で `main("final")` を呼び出してください。

コード上の入出力依存関係から見ると、実行順の目安は以下です。

1. 上部工座標を前処理します。

```bash
python scripts/preprocess/superstructure_coords.py
python scripts/preprocess/superstructure_common.py
```

2. 上部工の基本部材入力を作成します。

```bash
python scripts/preprocess/slab.py
python scripts/preprocess/main_girder.py
```

3. Grasshopper / Rhino で床版と主桁を生成します。

```text
scripts_gh/superstructure/const_slab.py
scripts_gh/superstructure/const_main_girder.py
```

この段階で、後続処理が参照する主桁点群、主桁上フランジ点、床版下面点などの pickle が出力されます。

4. 下部工の基本入力を作成します。

```bash
python scripts/preprocess/pier.py
python scripts/preprocess/abutment.py
```

5. Grasshopper / Rhino で橋脚柱、橋台、基礎などを生成します。

```text
scripts_gh/substructure/const_column.py
scripts_gh/substructure/const_piertop.py
scripts_gh/substructure/const_foundation.py
scripts_gh/substructure/const_abut.py
```

6. 床版・主桁・下部工から生成された点群を使う部材の入力を作成します。

```bash
python scripts/preprocess/cross_girder.py
python scripts/preprocess/barrier.py
python scripts/preprocess/shoe.py
python scripts/preprocess/I_box_joint.py
```

7. Grasshopper / Rhino で残りの上部工部材、支承、接続部を生成します。

```text
scripts_gh/superstructure/const_cross_girder.py
scripts_gh/superstructure/const_barriers.py
scripts_gh/substructure/const_shoe.py
scripts_gh/superstructure/const_I_box_joint.py
```

主な依存関係は以下です。

- `superstructure_common.py` は `superstructure_coords.py` の出力を読み込みます。
- `slab.py`, `main_girder.py`, `shoe.py` は `superstructure_common.py` の出力を読み込みます。
- `const_slab.py` は `slab.py` と `main_girder.py` の出力を読み込み、主桁上フランジ点と床版下面点を出力します。
- `const_main_girder.py` は `main_girder.py` と `const_slab.py` の出力を読み込み、主桁点群を出力します。
- `cross_girder.py` は `const_slab.py`, `const_main_girder.py`, `superstructure_common.py` の出力を読み込み、横桁用入力と `world_main_girder_points_IO` を出力します。
- `barrier.py` は `const_slab.py` の床版上面端部点を読み込みます。
- `I_box_joint.py` と `const_shoe.py` は `cross_girder.py` が出力する `world_main_girder_points_IO` を読み込みます。
- `const_piertop.py` は `pier.py` と `const_column.py` の出力を読み込みます。
- `const_shoe.py` は `shoe.py`, `const_abut.py`, `const_column.py`, `cross_girder.py` の出力を読み込みます。

実際の実行順は、作成する部材と Grasshopper 側で生成済みのデータに合わせて調整してください。

### 5. Grasshopper / Rhino で形状を生成する

`scripts_gh/` 以下のスクリプトは Rhino / Grasshopper の Python 実行環境を前提にしています。通常の Python インタープリタでは `Rhino` や `Rhino.Geometry` が利用できないため、そのまま実行できません。

`all.gh` を開き、Grasshopper 上で `scripts_gh/` 内のスクリプトを実行して、必要なジオメトリを生成・bake します。

## 出力ファイルの説明

前処理スクリプトは、設定された出力フォルダに主に以下の形式で出力します。

- `.xlsx`: 変換済み座標など、表形式の出力です。
- `.json`: dataclass などを JSON 化した確認用または連携用の出力です。
- `.pickle`: 後続の Python / Grasshopper スクリプトが読み込む中間データです。

コードから確認できる主な出力ファイル名は以下です。

- `superstructure_coords.xlsx`
- `input_superstructure_common.json` / `.pickle`
- `input_original_cross_girder_names.json` / `.pickle`
- `input_slab.json` / `.pickle`
- `input_slab_additional_points.json` / `.pickle`
- `input_main_girder.json` / `.pickle`
- `input_cross_girder.json` / `.pickle`
- `input_pier_indiv.json` / `.pickle`
- `input_pier_common.json` / `.pickle`
- `input_abut_indiv.json` / `.pickle`
- `input_abut_common.json` / `.pickle`
- `input_shoe.json` / `.pickle`
- `input_I_box_joint.json` / `.pickle`
- `world_main_girder_top_points.json` / `.pickle`
- `world_main_girder_points.json` / `.pickle`
- `world_main_girder_points_IO.json` / `.pickle`
- `world_slab_bottom_points.json` / `.pickle`
- `world_slab_up_top_points.json` / `.pickle`
- `world_slab_down_top_points.json` / `.pickle`
- `world_pier_top_points.json` / `.pickle`
- `world_abut_top_points.json` / `.pickle`
- `local_pier_column.json` / `.pickle`

## 注意事項

- 入力 Excel データは GitHub には含まれていません。
- サンプルデータが必要な場合は、著者に連絡すれば提供可能です。
- 個人環境に依存するパスは `.env` に記述し、GitHub には含めません。
- `initial` / `final` は、当初データと最終データの入力・出力フォルダを切り替えるために使います。
- `scripts_gh/` 以下のスクリプトは Rhino / Grasshopper 環境を前提にしています。
- 座標系・単位系の仕様は、使用する入力データに合わせて確認してください。

## English

## Purpose

This repository contains Python scripts for converting Excel-based road bridge parameters into intermediate data and Rhino / Grasshopper geometry-generation data.

The general workflow is to preprocess Excel inputs into JSON / pickle files, then load those intermediate files from Grasshopper / Rhino scripts to generate Rhino geometry such as Breps and Surfaces.

This repository is intended to support comparison between initial and final models. For that reason, many scripts provide `main("initial")` and `main("final")`. This argument mainly switches input and output directories.

## Repository Structure

```text
road-parametric-modeling/
├── all.gh
├── pyproject.toml
├── scripts/
│   └── preprocess/
├── scripts_gh/
│   ├── bake.py
│   ├── substructure/
│   └── superstructure/
└── src/
    └── my_project/
        ├── config/
        └── utils/
```

- `all.gh`: Grasshopper file used to run scripts under `scripts_gh/` and bake the generated geometry.
- `scripts/preprocess/`: preprocessing scripts that read Excel inputs and write JSON / pickle intermediate data.
- `scripts_gh/`: Rhino / Grasshopper-oriented geometry construction scripts.
- `scripts_gh/superstructure/`: geometry scripts for slab, main girders, cross girders, barriers, and I-girder / box-girder joints.
- `scripts_gh/substructure/`: geometry scripts for piers, abutments, columns, foundations, and bearings.
- `src/my_project/config/`: path settings, filename constants, and dataclass schemas.
- `src/my_project/utils/`: utilities for file I/O, coordinates, DataFrame processing, geometry calculations, and bake preparation.

## Main Scripts

### Preprocessing Scripts

The preprocessing scripts are under `scripts/preprocess/`. Most scripts call `main("initial")` when executed directly. `initial` and `final` switch the input and output folders for initial and final model data.

- `superstructure_coords.py`: converts superstructure local coordinates to world coordinates.
- `superstructure_common.py`: creates shared superstructure coordinate data.
- `slab.py`: creates slab input data.
- `main_girder.py`: creates main girder input data.
- `cross_girder.py`: creates cross beam, lateral bracing, and cross girder input/reference data.
- `barrier.py`: creates barrier and center barrier input data.
- `I_box_joint.py`: creates I-girder / box-girder joint input data.
- `pier.py`: creates individual and common pier input data.
- `abutment.py`: creates individual and common abutment input data.
- `shoe.py`: creates bearing and fall-prevention input data.

### Grasshopper / Rhino Scripts

Scripts under `scripts_gh/` load pickle files generated by preprocessing scripts and construct Rhino.Geometry objects. Many of them return `bake_keys` and `bake_objs` for baking in Grasshopper.

- `scripts_gh/superstructure/const_slab.py`: generates slab geometry and slab-related point data.
- `scripts_gh/superstructure/const_main_girder.py`: generates main girder point data and Breps.
- `scripts_gh/superstructure/const_cross_girder.py`: generates cross beam, lateral bracing, and cross girder Breps.
- `scripts_gh/superstructure/const_barriers.py`: generates barriers, center barriers, and nose geometry.
- `scripts_gh/superstructure/const_I_box_joint.py`: generates I-girder / box-girder joint geometry.
- `scripts_gh/substructure/const_column.py`: generates pier columns and pier top points.
- `scripts_gh/substructure/const_piertop.py`: generates pier top surfaces and related geometry.
- `scripts_gh/substructure/const_foundation.py`: generates footings, piles, and caisson foundations.
- `scripts_gh/substructure/const_abut.py`: generates abutment geometry and abutment reference points.
- `scripts_gh/substructure/const_shoe.py`: generates bearing and fall-prevention geometry.
- `scripts_gh/bake.py`: helper script for baking Breps into the active Rhino document.

## Input Data

Input Excel data is not included in GitHub. If sample data is needed, it can be provided by contacting the author.

## How to Run

### 1. Prepare Python

Python 3.9 or later is required.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

`pyproject.toml` defines the Python-side dependencies used by the repository: `pandas`, `numpy`, `openpyxl`, `matplotlib`, `python-dotenv`, `pyproj`, and `pyarrow`. Rhino / Grasshopper APIs are not normal pip dependencies and are expected to be available inside the Rhino / Grasshopper Python environment.

### 2. Configure Input and Output Paths

Input and output directories are defined in `src/my_project/config/paths.py`. Local paths should be configured in `.env`.

```powershell
Copy-Item .env.example .env
```

Set `ROAD_PARAMETRIC_RESEARCH_ROOT` in `.env` to the working directory that contains the initial and final data folders.

If needed, individual folders can be overridden with `ROAD_PARAMETRIC_INITIAL_DIR`, `ROAD_PARAMETRIC_INITIAL_INPUT_DIR`, `ROAD_PARAMETRIC_INITIAL_OUTPUT_DIR`, `ROAD_PARAMETRIC_FINAL_DIR`, `ROAD_PARAMETRIC_FINAL_INPUT_DIR`, and `ROAD_PARAMETRIC_FINAL_OUTPUT_DIR`.

### 3. Place Excel Inputs

Place the Excel inputs under the input folders configured in `.env`.

The Excel input data is not included in this GitHub repository. Contact the author if sample data is needed.

### 4. Run Preprocessing

Most scripts default to `main("initial")`. To process the final model data, call `main("final")` from the target script or Grasshopper.

Based on the input and output dependencies in the code, the recommended execution order is:

1. Preprocess superstructure coordinates.

```bash
python scripts/preprocess/superstructure_coords.py
python scripts/preprocess/superstructure_common.py
```

2. Create basic superstructure member inputs.

```bash
python scripts/preprocess/slab.py
python scripts/preprocess/main_girder.py
```

3. Generate slab and main girder data in Grasshopper / Rhino.

```text
scripts_gh/superstructure/const_slab.py
scripts_gh/superstructure/const_main_girder.py
```

This step outputs pickle files for downstream processes, including main girder points, top flange points, and slab bottom points.

4. Create basic substructure inputs.

```bash
python scripts/preprocess/pier.py
python scripts/preprocess/abutment.py
```

5. Generate pier columns, abutments, and foundations in Grasshopper / Rhino.

```text
scripts_gh/substructure/const_column.py
scripts_gh/substructure/const_piertop.py
scripts_gh/substructure/const_foundation.py
scripts_gh/substructure/const_abut.py
```

6. Create inputs for members that depend on generated slab, girder, and substructure point data.

```bash
python scripts/preprocess/cross_girder.py
python scripts/preprocess/barrier.py
python scripts/preprocess/shoe.py
python scripts/preprocess/I_box_joint.py
```

7. Generate the remaining superstructure members, bearings, and joints in Grasshopper / Rhino.

```text
scripts_gh/superstructure/const_cross_girder.py
scripts_gh/superstructure/const_barriers.py
scripts_gh/substructure/const_shoe.py
scripts_gh/superstructure/const_I_box_joint.py
```

Main dependencies:

- `superstructure_common.py` reads the output from `superstructure_coords.py`.
- `slab.py`, `main_girder.py`, and `shoe.py` read the output from `superstructure_common.py`.
- `const_slab.py` reads outputs from `slab.py` and `main_girder.py`, then writes main girder top flange points and slab bottom points.
- `const_main_girder.py` reads outputs from `main_girder.py` and `const_slab.py`, then writes main girder point data.
- `cross_girder.py` reads outputs from `const_slab.py`, `const_main_girder.py`, and `superstructure_common.py`, then writes cross girder inputs and `world_main_girder_points_IO`.
- `barrier.py` reads slab top edge points generated by `const_slab.py`.
- `I_box_joint.py` and `const_shoe.py` read `world_main_girder_points_IO` generated by `cross_girder.py`.
- `const_piertop.py` reads outputs from `pier.py` and `const_column.py`.
- `const_shoe.py` reads outputs from `shoe.py`, `const_abut.py`, `const_column.py`, and `cross_girder.py`.

Adjust the actual execution order based on the members being generated and the data already created in Grasshopper.

### 5. Generate Geometry in Grasshopper / Rhino

Scripts under `scripts_gh/` assume the Rhino / Grasshopper Python environment. They are not expected to run in a normal Python interpreter because they import `Rhino` and `Rhino.Geometry`.

Open `all.gh`, run the scripts under `scripts_gh/`, and bake the generated geometry as needed.

## Output Files

Preprocessing scripts mainly write the following formats to the configured output folders.

- `.xlsx`: tabular outputs such as converted coordinates.
- `.json`: serialized intermediate data, useful for inspection or external integration.
- `.pickle`: intermediate data consumed by later Python and Grasshopper scripts.

Main output names visible in the code include:

- `superstructure_coords.xlsx`
- `input_superstructure_common.json` / `.pickle`
- `input_original_cross_girder_names.json` / `.pickle`
- `input_slab.json` / `.pickle`
- `input_slab_additional_points.json` / `.pickle`
- `input_main_girder.json` / `.pickle`
- `input_cross_girder.json` / `.pickle`
- `input_pier_indiv.json` / `.pickle`
- `input_pier_common.json` / `.pickle`
- `input_abut_indiv.json` / `.pickle`
- `input_abut_common.json` / `.pickle`
- `input_shoe.json` / `.pickle`
- `input_I_box_joint.json` / `.pickle`
- `world_main_girder_top_points.json` / `.pickle`
- `world_main_girder_points.json` / `.pickle`
- `world_main_girder_points_IO.json` / `.pickle`
- `world_slab_bottom_points.json` / `.pickle`
- `world_slab_up_top_points.json` / `.pickle`
- `world_slab_down_top_points.json` / `.pickle`
- `world_pier_top_points.json` / `.pickle`
- `world_abut_top_points.json` / `.pickle`
- `local_pier_column.json` / `.pickle`

## Notes

- Input Excel data is not included in GitHub.
- If sample data is needed, it can be provided by contacting the author.
- Local paths should be written in `.env` and should not be committed to GitHub.
- `initial` and `final` switch input and output folders for initial and final model data.
- Scripts under `scripts_gh/` require the Rhino / Grasshopper Python environment.
- Coordinate system and unit conventions should be checked against the input data being used.
