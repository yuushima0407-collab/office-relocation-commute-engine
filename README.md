# CEST — Commute-burden Evaluation for Site Transfer

オフィス移転・多拠点配置の意思決定を、**通勤負荷・賃料・収容力のパレート最適**で支援するエンジン。

社員の居住駅分布と候補オフィス情報を入力すると、全組み合わせを列挙して制約フィルタを通し、トレードオフ上の最適案・ロバストネス分析・ベースライン比較を含む評価レポートを返す。

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

本番デプロイ済（AWS Lambda + API Gateway + S3 + CloudFront、詳細は [`cest/docs/aws-architecture.md`](cest/docs/aws-architecture.md)）。

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | ヘルスチェック |
| `POST` | `/evaluate` | 評価実行 → EvaluationReport |
| `POST` | `/parse-csv` | CSV/TSV テキストをパースして候補リスト化 |
| `POST` | `/parse-csv/upload` | CSV/Excel ファイルアップロードをパース |

### リクエスト例

```bash
curl -X POST http://localhost:8000/evaluate \
  -H "Content-Type: application/json" \
  -d @cest/tests/fixtures/demo_3candidates.json
```

### レスポンス概要（v0.3.3）

```
EvaluationReport
├── all_combinations[]      全候補組み合わせ（賃料・通勤KPI・収容率・部署内訳・部署間アラート）
├── pareto_frontier_ids[]   パレート最適案のID（3軸: 賃料・平均通勤・総定員）
├── constraints_impact      フィルタ段階ごとの絞り込み数（無駄拠点・収容・予算・通勤）
├── robustness[]            最適案ごとの「賃料許容上昇額・収容余裕」
├── baseline_diagnosis      現オフィス指定時の収容率・通勤統計・改善余地
└── notices[]               入力不備・到達不能駅・カバレッジ警告
```

## Architecture

```
POST /evaluate
  │
  ▼
EvaluateRequest (Pydantic v2 validation)
  │
  ▼
combination.run_v3_pipeline()
  ├── 組み合わせ列挙        ── N候補からK拠点を列挙
  ├── 部署配置             ── 各組み合わせに対し部署を割り当て
  ├── 制約フィルタ          ── 収容/予算/通勤上限/希望定員/無駄拠点除外
  ├── パレート抽出          ── 賃料 × 平均通勤 × 総定員の3軸
  ├── robustness 計算       ── 案ごとの賃料許容額・収容余裕
  ├── baseline 比較         ── 現オフィス指定時の改善余地
  └── explain 生成          ── 自然言語の説明・アラート
  │
  ▼
EvaluationReport (JSON)
```

## Project Structure

```
cest/
├── src/cest/
│   ├── main.py                  FastAPI app + Mangum (Lambda adapter)
│   ├── routes/
│   │   ├── evaluate.py          POST /evaluate
│   │   └── parse_csv.py         POST /parse-csv, /parse-csv/upload
│   ├── models/request.py        Pydantic request models
│   ├── engine/
│   │   ├── pipeline.py          評価エントリポイント
│   │   ├── combination.py       コア: パレート・robustness・baseline
│   │   ├── routing.py           Dijkstra経路探索
│   │   ├── kpi.py               通勤時間KPI算出
│   │   ├── csv_parser.py        CSV/TSV/Excel解析
│   │   ├── fare_estimator.py    JR IC運賃推定
│   │   ├── explain_pack.py      説明テキスト生成
│   │   ├── ranking.py           スコアリング補助
│   │   ├── graph_loader.py      グラフ/駅マスタ読込
│   │   └── notices.py           Notice収集
│   ├── utils/
│   │   └── schema_validate.py   JSON Schema検証
│   └── data/
│       ├── tokyo_core_v1.json   駅ネットワークグラフ
│       └── station_master.json  駅マスタ
├── schemas/                     レスポンス JSON Schema
├── tests/                       28 tests (pytest)
└── docs/
    ├── aws-architecture.md      インフラ設計書
    ├── v0.3.3-frontend.md       v0.3.3 フロント仕様
    ├── v0.3.3-sample-data.md    サンプルデータ仕様
    └── v0.4-spec.md             v0.4 ロードマップ
```

## Design Decisions

**パレート最適 + 制約フィルタ** — 重み付きスコアではなく、賃料・平均通勤・総定員の 3 軸でパレートフロンティアを抽出。意思決定者がトレードオフを見て選ぶ設計。

**決定論の保証** — 同じ入力に対して常に同じ出力を返す。テストで検証。

**Notice system** — 入力の不備や制約違反は `notices[]` で構造化して返す。エラーで止めず、計算可能な範囲を返してクライアントに判断材料を渡す。

**Robustness（感度ではなく注意点として）** — 「賃料がいくら上がるとパレートから脱落するか」「収容にどれだけ余裕があるか」を案ごとに算出。専門用語の感度分析ではなく自然言語の注意点として提示。

**AWS サーバーレス構成** — 常時稼働コストゼロ。API Gateway HTTP API + Lambda + S3 + CloudFront で月170円程度。Mangum で FastAPI をそのまま動かす。詳細は [aws-architecture.md](cest/docs/aws-architecture.md)。

## Tests

```bash
cd cest && pytest -v
```

| カテゴリ | 検証内容 |
|---|---|
| `test_determinism` | 同一入力 → 同一出力、レスポンス構造の整合 |
| `test_logic` | パレート判定・robustness・部署間アラート |
| `test_monotonicity` | 通勤時間と評価の単調性 |
| `test_unreachable` | 到達不能駅の処理 |
| `test_csv_parser` | CSV/TSV/Excel 解析 |
| `test_backward_compat_v1_request` | 旧バージョンリクエストの後方互換 |

## Tech Stack

- **Backend**: Python 3.11 / FastAPI / Pydantic v2 / NetworkX / pytest
- **Infra**: AWS (S3 + CloudFront + API Gateway HTTP API + Lambda + Mangum)
- **Tools**: Git / GitHub / JSON Schema (Draft 2020-12)

## License

Private
