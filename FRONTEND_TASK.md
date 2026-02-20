# Frontend: CEST 比較UIの実装

## CESTとは

企業がオフィス移転を検討するとき、候補地ごとの**通勤負荷を定量比較**するツール。
バックエンド（Python/FastAPI）は完成済みで、`POST /evaluate` に候補オフィスと社員の居住駅分布を投げると、KPI・ランキング・説明文を返す。

フロントエンドは `cest/web/` に作成する。
mainには触らず、自分用のブランチ（feature/xxx）を作る
変更はそのブランチに コミットしてpush する（途中でもOK）
pushしたら ブランチ名を連絡（私がそれを見て動作確認する）

## バックエンドAPI

```
GET  /health       → {"ok": true}
POST /evaluate     → EvaluationReport (JSON)
```

### 起動方法

```bash
cd cest
pip install -e ".[dev]"
uvicorn cest.main:app --reload --port 8000
```

Swagger UI: http://localhost:8000/docs

### リクエスト例

`cest/tests/fixtures/demo_3candidates.json` がそのまま使える。

```json
{
  "inputs": {
    "office_candidates": [
      {"office_id": "shinagawa", "name": "品川オフィス", "nearest_station_id": "shinagawa", "last_mile_minutes": 5, "lat": 35.6285, "lon": 139.7388, "rent_jpy_month": 8000000},
      {"office_id": "shibuya", "name": "渋谷オフィス", ...},
      {"office_id": "toyosu", "name": "豊洲オフィス", ...}
    ],
    "home_station_distribution": [
      {"station_id": "kawasaki", "count": 45},
      {"station_id": "omiya", "count": 30},
      ...
    ],
    "policy_as_is": {"office_days_per_week": 3},
    "settings": {
      "baseline_office_id": "shinagawa",
      "ranking_weights": {"access": 0.6, "financial": 0.3, "environmental": 0.1},
      ...
    }
  }
}
```

### レスポンス構造（重要な部分のみ）

完全なサンプルは `cest/tests/fixtures/demo_3candidates_response.json` を参照。
JSON Schemaは `cest/schemas/evaluation_report_v0.1.2.json` にある。

```
{
  "baseline_scenario_id": "scenario_shinagawa",

  "results": [               ← オフィス候補ごとに1つ
    {
      "scenario_id": "scenario_shinagawa",
      "office_id": "shinagawa",
      "kpis": {
        "trip_minutes":       {"avg": 31.3, "p50": 23, "p95": 62},
        "round_trip_minutes": {"avg": 62.6, "p50": 46, "p95": 124},
        "weekly_minutes":     {"avg": 187.7, "p50": 138, "p95": 372},
        "thresholds": [
          {"trip_minutes": 60, "exceed_count": 20, "exceed_share": 0.111},
          {"trip_minutes": 90, "exceed_count": 0, "exceed_share": 0.0}
        ]
      },
      "station_breakdown": [  ← 駅ごとの詳細（Cesium駅柱に使う）
        {"station_id": "kawasaki", "count": 45, "trip_minutes": 14,
         "reachable": true, "delta_vs_baseline_trip_minutes": null},
        ...
      ]
    },
    ...
  ],

  "ranking": {
    "weights_normalized": {"access": 0.6, "financial": 0.3, "environmental": 0.1},
    "axes": {
      "access":        [{"scenario_id": "...", "score_0_100": 31.1}, ...],
      "financial":     [{"scenario_id": "...", "score_0_100": 20.0}, ...],
      "environmental": [{"scenario_id": "...", "score_0_100": null}, ...]
    },
    "overall": [
      {"scenario_id": "scenario_toyosu", "overall_score_0_100": 28.7},
      ...
    ],
    "best_scenario_id": null   ← 感度分析がunstableのときnull
  },

  "explain_pack": {
    "tradeoffs": ["豊洲オフィスは家賃が月2,000,000円 安い", "..."],
    "if_you_prioritize": {
      "access": ["scenario_shinagawa"],
      "financial": ["scenario_toyosu"]
    }
  },

  "sensitivity": {
    "robust": false,
    "flip_rate": 0.111,
    "summary": "前提を±5分変えると、11%のケースで1位が変わります。..."
  },

  "notices": [
    {"level": "warning", "code": "SENSITIVITY_UNSTABLE", "message": "...", "action": "..."}
  ]
}
```

## 実装してほしいこと

### 1. 入力フォーム
- オフィス候補（2〜5件）: 名前、最寄駅、徒歩分、家賃
- 居住駅分布（N件）: 駅名、人数
- ポリシー: 出社日数/週
- 「評価実行」ボタンで `POST /evaluate` を叩いて結果を表示する

### 2. 結果の比較表
- オフィス候補を横に並べて KPI を比較する表
- 片道 avg/p50/p95、往復、週間、閾値超過率、スコア
- 最良値のハイライトがあると見やすい

### 3. 重みスライダー（クライアント側再計算）
- access / financial / environmental の3スライダー
- **スライダーを動かしたら API を叩き直さず、クライアント側で overall_score を再計算する**
- 計算式: `overall = Σ(weight[axis] * score[axis]) / Σ(weight[axis])` （score が null の軸は飛ばす）
- 比較表のランキングが即時更新されること

### 4. 通知バナー（notices）
- `error` → 赤、`warning` → 黄、`info` → グレー

### 5. 説明パック表示
- tradeoffs（トレードオフ文）
- if_you_prioritize（「〇〇を重視するなら → △△」）
- sensitivity の summary

### 6. Cesium 3D 可視化
- 駅柱ビュー: 高さ = 人数、色 = 所要時間帯（<60分 青、60-90 黄、>90 赤、unreachable グレー）
- Delta View: ベースラインとの差分（悪化=赤、改善=青）
- オフィスマーカー
- 絶対値 / 差分 のトグル切替

駅の座標データは `cest/src/cest/data/station_master.json` にある。

### 7. デモモード
- ページ読み込み時に `GET /health` を呼んで、失敗したらデモモードに切り替える
- デモモードではリクエスト・レスポンスを埋め込み済みデータで表示する
- バックエンドなしでも動作確認できるようにするため

## 参考

| ファイル | 内容 |
|---------|------|
| `cest/tests/fixtures/demo_3candidates.json` | デモ用リクエスト |
| `cest/tests/fixtures/demo_3candidates_response.json` | デモ用レスポンス |
| `cest/schemas/evaluation_report_v0.1.2.json` | レスポンスの JSON Schema |
| `cest/src/cest/data/station_master.json` | 56駅の座標（駅柱表示用） |
| `apps/web/` | 別プロジェクトの Cesium 実装例（PLATEAU建物、MapTiler、駅柱パターン） |

## 技術的な制約・方針

- `cest/web/` に作成する。既存の `cest/src/` 配下は変更しない
- ビルドステップなしで動くこと（vanilla JS + ES modules、または軽量フレームワーク）
- Cesium は CDN から読み込む（`https://cesium.com/downloads/cesiumjs/releases/1.124/Build/Cesium/Cesium.js`）
- MapTiler キーは `apps/web/main.js` の先頭にある

## 受け入れ条件

- [ ] `cest/web/index.html` をHTTPサーバ経由で開いて動作すること
- [ ] デモモード: バックエンドなしで比較表・駅柱が表示される
- [ ] APIモード: バックエンド起動時に「評価実行」で実際の結果が表示される
- [ ] 重みスライダーを動かしてランキングが即時更新される（APIコールなし）
- [ ] Delta View トグルで赤/青の差分表示に切り替わる
