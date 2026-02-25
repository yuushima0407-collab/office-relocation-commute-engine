# CEST v0.3 フロントエンド実装タスク

## 背景

CEST は企業のオフィス移転・多拠点配置を支援するツールです。バックエンドAPIはすでに完成しており、フロントエンドをゼロから実装してもらいます。

ユーザーは総務・経営企画担当者（非エンジニア）。技術用語を使わず、制約を試行錯誤しながら意思決定できる画面が必要です。

## 技術制約

- バニラ JS + HTML + CSS のみ（フレームワーク・ビルドツール不要）
- `web/` ディレクトリに配置
- API: `http://localhost:8001`

## ユーザーストーリー

1. **初回確認**: 社員データとオフィス候補を入力したら、全組み合わせのトレードオフを一覧で確認したい
2. **制約追加**: 「このオフィスは必ず使う」「この部署は同じ拠点にしたい」などの条件を加えながら絞り込みたい
3. **案の比較**: 気になる2案を並べて通勤・コストの差を確認したい
4. **地図確認**: どの駅の社員が何分かかるかを地図上で視覚的に確認したい
5. **結果の信頼性確認**: この結果を前提にして意思決定してよいか判断したい

## APIインターフェース

### POST /evaluate — リクエスト

```json
{
  "inputs": {
    "home_station_distribution": [
      { "station_id": "omiya", "count": 5, "group": "開発" }
    ],
    "office_candidates": [
      {
        "office_id": "shinagawa",
        "name": "品川オフィス",
        "nearest_station_id": "shinagawa",
        "last_mile_minutes": 3.0,
        "rent_jpy_month": 3000000,
        "floor_area_sqm": 500
      }
    ],
    "policy_as_is": { "office_days_per_week": 3.0 },
    "settings": {
      "num_offices": [1, 2],
      "fixed_offices": [],
      "fixed_assignment": [{ "group": "営業", "office_id": "shinagawa" }],
      "group_together": [["開発", "企画"]],
      "budget_total_rent_jpy_month": null,
      "max_p95_trip_minutes": null,
      "max_avg_trip_minutes": null
    }
  }
}
```

### POST /evaluate — レスポンス

```json
{
  "version": "v0.3",
  "all_combinations": [
    {
      "combination_id": "k2_combo_1",
      "selected_offices": ["shinagawa", "omiya"],
      "num_offices": 2,
      "total_rent_jpy_month": 4800000,
      "p95_trip_minutes": 48.0,
      "avg_trip_minutes": 32.0,
      "total_population": 125,
      "exceed_60_count": 0,
      "exceed_90_count": 0,
      "distribution": { "under_30": 45, "30_to_60": 80, "60_to_90": 0, "over_90": 0 },
      "is_pareto_optimal": true,
      "assignment": [
        { "group": "営業", "assigned_office_id": "shinagawa", "population": 30, "capacity_headroom": 70, "capacity_estimated": true }
      ],
      "per_office": [
        {
          "office_id": "shinagawa",
          "name": "品川オフィス",
          "assigned_population": 80,
          "capacity": 150,
          "capacity_headroom": 70,
          "capacity_estimated": true,
          "rent_jpy_month": 3000000,
          "station_breakdown": [
            { "station_id": "omiya", "trip_minutes": 35.0, "count": 5, "reachable": true }
          ]
        }
      ],
      "explain": {
        "commute": { "headline": "平均通勤32分、最も長い人でも48分", "detail": "社員125人中、60分超えは0人", "distribution": "30分未満: 45人 / 30-60分: 80人 / 60分超: 0人" },
        "cost": { "headline": "月額480万円", "detail": "品川300万 + 大宮180万" },
        "capacity": { "headline": "両拠点とも収容可能", "detail": "品川: 80人配置、推定収容150人（余裕70人）", "warning": "大宮は余裕が少なく...", "note": "※推定値。..." },
        "assignment": { "headline": "4部署の配置", "detail": ["品川 → 営業部(30人)"], "rationale": "各部署を通勤負荷が最小になるオフィスに配置" },
        "vs_alternatives": ["品川1拠点にすると月100万安いが通勤最長+24分"]
      }
    }
  ],
  "pareto_frontier_ids": ["k2_combo_1"],
  "constraints_impact": {
    "total_combinations": 23,
    "after_capacity_filter": 18,
    "after_budget_filter": 15,
    "after_commute_filter": 12,
    "pareto_optimal": 5,
    "vs_previous_round": null
  },
  "sensitivity": {
    "ranking_stable": true,
    "summary": "ラストマイルを±5分変動させても順位は変わりません。",
    "details": [
      { "parameter": "last_mile_minutes ±5min", "ranking_changed": false, "description": "全パレート最適案がフロンティア上に維持" }
    ]
  },
  "notices": [
    { "level": "warning", "code": "HAZARD_WARNING", "message": "渋谷駅: 浸水想定区域（0.8m）..." }
  ]
}
```

APIはレスポンスに `inputs` を含まないため、リクエスト時の `inputs` をフロント側で保持して使うこと。

### GET /health

```json
{ "ok": true }
```

### 静的ファイル（`web/` に既存）

| ファイル | 内容 |
|---|---|
| `demo_response.json` | デモ用レスポンス（`inputs` フィールド付き） |
| `station_master.json` | 駅マスタ `{ stations: [{ station_id, name, lat, lon }] }` |

## 受け入れ条件

### 基本フロー
- [ ] デモデータを読み込むと全候補の一覧と主要KPIが表示される
- [ ] 制約を設定して再計算すると候補が絞り込まれ、変化が分かる
- [ ] APIに繋がらない状態でもデモデータで動作する

### 候補の把握
- [ ] 全候補が**通勤×月額賃料の2軸散布図**で表示され、トレードオフを一目で把握できる
- [ ] 各案の通勤（平均・p95・分布）とコスト（月額・拠点別内訳）と合計収容人数を確認できる
- [ ] どの部署がどのオフィスに配置されるかと、収容余裕を確認できる
- [ ] 2案を選んで通勤・コストの差分を比較できる

### 地図
- [ ] 選択した案の各駅の社員が地図上に通勤時間と人数付きで表示される
- [ ] オフィス位置がマーカーで表示される

### 感度分析・通知
- [ ] 結果が安定しているか不安定かが一目で分かる
- [ ] ハザードなどの通知が表示される

## スコープ外

- モバイル対応
- 社員データ・オフィスデータの入力フォーム（別タスク）
- 認証・永続化
