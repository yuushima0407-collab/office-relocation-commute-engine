# CEST — Commute-burden Evaluation for Site Transfer

オフィス移転・多拠点配置の意思決定を、**通勤負荷・賃料・収容力のパレート最適**で支援するエンジン。

社員の居住駅分布と候補オフィス情報を入力すると、全組み合わせを列挙して制約フィルタを通し、トレードオフ上の最適案・収容余裕分析・ベースライン比較を含む評価レポートを返す。

<img width="1280" height="658" alt="image" src="https://github.com/user-attachments/assets/94e42435-9a4c-48f9-8633-4260bcbd1b08" />
<img width="1273" height="657" alt="image" src="https://github.com/user-attachments/assets/dab003a2-a194-4e2c-800d-4b89cbd3ecba" />
<img width="1278" height="664" alt="image" src="https://github.com/user-attachments/assets/502a8923-1a62-41c0-856c-00621015f208" />


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

社員名簿・オフィス一覧のCSV/TSV取り込みはバックエンドAPIを持たず、フロントエンド（`web/index.html`）だけで完結する。

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
├── capacity_headroom[]     最適案ごとの収容余裕・ボトルネック
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
pipeline.evaluate()          ── 入力検証・警告収集
  │
  ▼
combination.run_v3_pipeline()
  ├── 組み合わせ列挙        ── N候補からK拠点を列挙
  ├── 部署配置             ── 各組み合わせに対し部署を割り当て
  ├── 制約フィルタ          ── 収容/予算/通勤上限/希望定員/無駄拠点除外
  ├── パレート抽出          ── 賃料 × 平均通勤 × 総定員の3軸
  ├── 収容余裕分析          ── 案ごとの収容余裕・ボトルネック
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
│   │   └── evaluate.py          POST /evaluate
│   ├── models/request.py        Pydantic request models
│   ├── engine/
│   │   ├── pipeline.py          評価エントリポイント（入力検証・警告収集）
│   │   ├── combination.py       司令塔（run_v3_pipeline。combo/*.py を順番に呼ぶだけ）
│   │   ├── combo/
│   │   │   ├── enumeration.py   組み合わせ列挙
│   │   │   ├── assignment.py    部署配置
│   │   │   ├── evaluation.py    1組み合わせのKPI評価
│   │   │   ├── department.py    部署別内訳・対立警告
│   │   │   ├── pareto.py        パレートフロンティア抽出
│   │   │   ├── capacity.py      収容余裕分析
│   │   │   ├── baseline.py      Before/After比較
│   │   │   ├── explain.py       自然言語の説明生成
│   │   │   └── common.py        combo/* 共通ヘルパー
│   │   └── support/
│   │       ├── routing.py       Dijkstra経路探索
│   │       ├── kpi.py           通勤時間KPI算出
│   │       ├── fare_estimator.py JR IC運賃推定
│   │       ├── graph_loader.py  グラフ/駅マスタ読込
│   │       └── notices.py       Notice収集
│   ├── utils/
│   │   └── schema_validate.py   JSON Schema検証
│   └── data/
│       ├── tokyo_core_v1.json   駅ネットワークグラフ
│       └── station_master.json  駅マスタ
├── schemas/                     レスポンス JSON Schema
├── tests/                       30 tests (pytest)
└── docs/
    ├── aws-architecture.md      インフラ設計書
    ├── v0.3.3-frontend.md       v0.3.3 フロント仕様
    ├── v0.3.3-sample-data.md    サンプルデータ仕様
    └── v0.4-spec.md             v0.4 ロードマップ

web/
└── index.html                   本番フロントエンド（CSV取り込み・地図表示・評価結果UI）
```

## Design Decisions

**パレート最適 + 制約フィルタ** — 重み付きスコアではなく、賃料・平均通勤・総定員の 3 軸でパレートフロンティアを抽出。意思決定者がトレードオフを見て選ぶ設計。

**決定論の保証** — 同じ入力に対して常に同じ出力を返す。テストで検証。

**Notice system** — 入力の不備や制約違反は `notices[]` で構造化して返す。エラーで止めず、計算可能な範囲を返してクライアントに判断材料を渡す。

**収容余裕分析（感度ではなく注意点として）** — 「収容にどれだけ余裕があるか」「推定定員の場合は下振れリスクがないか」を案ごとに算出。専門用語の感度分析ではなく自然言語の注意点として提示。旧「賃料耐性」は2026-07に削除——候補が少ない現実的な規模では数値が出るケースが3割程度しかなく、かつ散布図で視覚的にわかる情報とほぼ重複していたため。

**AWS サーバーレス構成** — 常時稼働コストゼロ。API Gateway HTTP API + Lambda + S3 + CloudFront で月170円程度。Mangum で FastAPI をそのまま動かす。詳細は [aws-architecture.md](cest/docs/aws-architecture.md)。

## Tests

```bash
cd cest && pytest -v
```

| カテゴリ | 検証内容 |
|---|---|
| `test_determinism` | 同一入力 → 同一出力、レスポンス構造の整合 |
| `test_logic` | パレート判定・収容余裕・部署間アラート |
| `test_monotonicity` | 通勤時間と評価の単調性 |
| `test_unreachable` | 到達不能駅の処理 |
| `test_routing_robustness` | 1人の駅が不正でも部署全体が配置不能にならないこと |
| `test_station_aggregation` | 同一駅に複数部署がいても人数が二重集計されないこと |
| `test_backward_compat_v1_request` | 旧バージョンリクエストの後方互換 |

## Tech Stack

- **Backend**: Python 3.11 / FastAPI / Pydantic v2 / NetworkX / pytest
- **Infra**: AWS (S3 + CloudFront + API Gateway HTTP API + Lambda + Mangum)
- **Tools**: Git / GitHub / JSON Schema (Draft 2020-12)

## License

Private
