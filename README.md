# CEST — Commute-burden Evaluation for Site Transfer

オフィス移転候補地ごとの**通勤負荷を定量比較**するバックエンドエンジン。

社員の居住駅分布と候補オフィス情報を入力すると、通勤時間KPI・ランキング・感度分析・説明テキストを含む評価レポートを返す。

## Quick Start

```bash
cd cest
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -e ".[dev]"

# テスト
pytest

# APIサーバ起動
uvicorn cest.main:app --reload --port 8000
```

Swagger UI: http://localhost:8000/docs

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | ヘルスチェック |
| `POST` | `/evaluate` | 評価実行 → EvaluationReport |

### リクエスト例

```bash
curl -X POST http://localhost:8000/evaluate \
  -H "Content-Type: application/json" \
  -d @cest/tests/fixtures/demo_3candidates.json
```

### レスポンス概要

```
EvaluationReport
├── results[]              シナリオ別KPI
│   ├── kpis               片道/往復/週間 (avg, p50, p95)
│   ├── station_breakdown  駅ごとの所要時間・人数
│   └── unreachable        到達不能駅の一覧
├── ranking                重み付きスコア・総合ランキング
├── explain_pack           トレードオフ文・優先軸別の推奨
├── sensitivity            感度分析 (robust / flip_rate)
└── notices[]              警告・エラー通知
```

完全なJSON Schemaは [`cest/schemas/evaluation_report_v0.1.2.json`](cest/schemas/evaluation_report_v0.1.2.json) を参照。

## Architecture

```
POST /evaluate
  │
  ▼
EvaluateRequest (Pydantic validation)
  │
  ▼
pipeline.evaluate()
  ├── graph_loader    ── 駅ネットワークグラフ (NetworkX)
  ├── routing         ── Dijkstra最短経路
  ├── kpi             ── 片道/往復/週間/閾値超過
  ├── ranking         ── access + financial + environmental 軸スコア
  ├── sensitivity     ── ラストマイル±5分で1位が変わるか
  ├── explain_pack    ── トレードオフ文・推奨テキスト生成
  └── notices         ── 入力不備・カバレッジ警告の収集
  │
  ▼
EvaluationReport (JSON Schema v0.1.2)
```

## Project Structure

```
cest/
├── src/cest/
│   ├── main.py                  FastAPI app
│   ├── routes/evaluate.py       POST /evaluate
│   ├── models/request.py        Pydantic request models
│   ├── engine/
│   │   ├── pipeline.py          メインパイプライン
│   │   ├── routing.py           Dijkstra経路探索
│   │   ├── kpi.py               KPI算出
│   │   ├── ranking.py           スコアリング・ランキング
│   │   ├── sensitivity.py       感度分析
│   │   ├── explain_pack.py      説明テキスト生成
│   │   ├── graph_loader.py      グラフ/駅マスタ読込
│   │   └── notices.py           Notice収集
│   ├── utils/
│   │   └── schema_validate.py   JSON Schema検証
│   └── data/
│       ├── tokyo_core_v1.json   駅ネットワークグラフ
│       └── station_master.json  56駅の座標データ
├── schemas/
│   └── evaluation_report_v0.1.2.json
├── tests/
│   ├── test_determinism.py      決定論テスト + Schema適合
│   ├── test_monotonicity.py     単調性テスト
│   ├── test_unreachable.py      到達不能駅の処理テスト
│   └── fixtures/
│       ├── demo_3candidates.json           デモ入力
│       └── demo_3candidates_response.json  デモ出力
└── pyproject.toml
```

## Design Decisions

**決定論の保証** — 同じ入力に対して常に同じ出力を返す。ランダム性・非決定的処理はない。テストで検証済み。

**Contract-first** — JSON Schema v0.1.2がレスポンス構造のSSoT（Single Source of Truth）。バックエンドの出力はテストでSchemaに対して検証される。

**Notice system** — 入力の不備や制約違反を `notices[]` で構造化して返す。エラーで落とすのではなく、可能な範囲で計算を続行し、問題点をクライアントに伝える。

**Sensitivity analysis** — ラストマイル（徒歩分数）を±5分変動させて1位が変わるかを検証する。不安定な場合は `best_scenario_id = null` を返し、結論の信頼度をクライアントに示す。

## Tests

```bash
cd cest && pytest -v
```

| テスト | 検証内容 |
|--------|---------|
| `test_determinism` | 同一入力 → 同一出力 |
| `test_determinism::schema` | 出力がJSON Schema v0.1.2に適合 |
| `test_monotonicity` | 通勤時間が長い → accessスコアが低い |
| `test_unreachable` | 到達不能駅がKPIから除外される |

## Frontend

フロントエンドは未実装。実装タスクは [FRONTEND_TASK.md](FRONTEND_TASK.md) を参照。

## Tech Stack

- Python 3.11+
- FastAPI + Pydantic v2
- NetworkX（駅間Dijkstra経路探索）
- jsonschema（レスポンス検証）

## License

Private
