# CEST v2 仕様書 — マルチオフィス最適化 + ハザード軸

## Context

CEST v1 は「候補A vs B の通勤負荷比較」。v2では以下を追加し「最適化エンジン」に格上げ：

1. **マルチオフィス最適化** — N候補からK拠点の最適組み合わせ + 部署割り当て
2. **ハザード軸** — 国土交通省の公的災害リスクデータによるBCP評価
3. **通勤悪化分布Notice** — 移転時の社員影響を事実ベースで提示
4. **CSV入力** — 企業の人事データを直接投入

---

## v1 → v2 差分

| 項目 | v1 | v2 |
|------|-----|-----|
| 拠点数 | 1（候補比較） | K拠点（組み合わせ最適化） |
| 評価軸 | access, financial | access, financial, hazard |
| 社員グループ | なし | group列（任意、同グループは同拠点） |
| 予算制約 | なし | 総賃料上限フィルタ |
| 拠点固定 | baseline_office_id | fixed_offices[] |
| 部署配置固定 | なし | fixed_assignment（任意） |
| 初期表示 | 重みつきランキング | KPI比較表のみ（ランキングなし） |
| 重み調整後 | ランキング更新 | ランキング初表示 |
| 入力 | JSONのみ | JSON + CSV |

---

## 設計方針

### デフォルトではランキングを出さない

v1のデフォルト重み(access=0.6, financial=0.3)には根拠がない。

v2の方針:
1. 初期表示: 各軸のスコアを並べたKPI比較表のみ
2. ユーザーが重みスライダーを調整 → ランキングを生成・表示
3. 「あなたの重み設定によるランキング」と明示

### 拠点数別サマリ

K=1,2,3,...の結果を比較するサマリを出す。「おすすめ」は言わない。
定量的な差分（通勤改善率、コスト増加率）を計算して判断材料を提示:

```
拠点数 | 通勤P95 | 総賃料    | 差分
1拠点  | 72分    | 300万/月  | —
2拠点  | 45分    | 480万/月  | 通勤-37%, 賃料+60%
3拠点  | 38分    | 650万/月  | 通勤-16%, 賃料+35%

※ 各拠点の収容人数・設備は考慮していません
```

---

## 1. リクエストスキーマ変更

### v2 追加フィールド
```json
{
  "inputs": {
    "home_station_distribution": [
      {"station_id": "omiya", "count": 5, "group": "開発"}
    ],
    "office_candidates": [ ... ],
    "policy_as_is": {"office_days_per_week": 3},
    "settings": {
      "num_offices": [1, 2, 3],
      "fixed_offices": ["shinagawa"],
      "fixed_assignment": {"開発": "omiya"},
      "budget_total_rent_jpy_month": null,
      "ranking_weights": null
    }
  }
}
```

### 新規フィールド詳細
- `group`: 社員のグループ（部署等）。任意。同グループは同拠点に割り当て
- `num_offices`: 評価する拠点数のリスト。デフォルト[1]
- `fixed_offices`: 必ず選ばれるオフィスID。任意
- `fixed_assignment`: グループをオフィスに固定。任意。例: `{"開発": "omiya"}`
- `budget_total_rent_jpy_month`: 総賃料上限。nullなら制約なし
- `ranking_weights`: nullならランキング非生成。指定時のみ生成
- `ranking_weights.hazard`: ハザード軸の重み（追加）

### 後方互換性
- 全追加フィールド省略可。v1リクエストをそのままv2に投げても動く
- `num_offices`省略→[1]、`group`省略→個人単位、`ranking_weights`省略→null

---

## 2. マルチオフィス最適化アルゴリズム

### 処理フロー
```
各K（拠点数）について:

1. 候補M箇所からK拠点の全組み合わせを列挙
   - fixed_offices を含む組み合わせのみ
   - C(M-F, K-F) 通り

2. 各組み合わせについて:
   a. 予算フィルタ: 総賃料 > budget なら除外
   b. 部署割り当て:
      - fixed_assignment のグループ → 指定オフィスに固定
      - 残りのグループ → 最寄りオフィスに割り当て（これが最適）
      - group列なし → 各社員を最寄りオフィスに割り当て
   c. 各拠点ごとに KPI 計算（v1のkpi.pyをそのまま使う）
   d. 全拠点の加重平均で組み合わせ全体のKPIを算出

3. 各K内で組み合わせをaccess順にソートして返す
```

### なぜ部署割り当ての全パターンを見なくていいか

全社の通勤合計 = 各部署の通勤合計の足し算。
各部署の通勤は他の部署に影響しない（容量制約なし）。
→ 各部署を独立に最寄りオフィスに送れば全体最適。

部署100個、オフィス3個でも O(100 × 3) の距離計算だけで済む。

### ユーザーによる部署配置変更

ユーザーが「開発は大宮にしたい」と指定 → `fixed_assignment` に入れて再計算。
その制約を固定した上で、残りの部署は最寄りオフィスに割り当て。

---

## 3. ハザード軸

### データソース
国土交通省 ハザードマップポータル
- 洪水浸水想定区域（想定最大規模）
- 地震危険度（東京都）

### スコア計算
```python
def hazard_score(office_candidate) -> float:
    """0-100。高いほど安全。"""
    flood_depth = station_hazard[station_id]["flood_depth_m"]
    seismic_rank = station_hazard[station_id]["seismic_rank"]

    flood_score = interpolate(flood_depth, [(0,100),(0.5,70),(1,50),(3,10),(5,0)])
    seismic_score = (5 - seismic_rank) * 25 if seismic_rank else None

    return mean_of_available(flood_score, seismic_score)
```

### データ
56駅分を事前取得してJSON埋め込み: `cest/src/cest/data/station_hazard.json`

---

## 4. レスポンススキーマ (v0.2.0)

```json
{
  "version": "v0.2.0",
  "generated_at": "...",
  "inputs": { ... },

  "by_num_offices": {
    "1": {
      "combinations": [
        {
          "combination_id": "k1_combo_1",
          "selected_offices": ["shinagawa"],
          "total_rent_jpy_month": 3000000,
          "assignment": [
            {"group": "開発", "assigned_office_id": "shinagawa", "population": 50}
          ],
          "per_office_results": [
            {
              "office_id": "shinagawa",
              "assigned_population": 50,
              "kpis": { ... },
              "station_breakdown": [ ... ],
              "hazard": {"score_0_100": 65, "flood_depth_m": 0.5, "seismic_rank": 3}
            }
          ],
          "aggregate_kpis": { ... },
          "axis_scores": {"access": 78.5, "financial": 62.0, "hazard": 65.0}
        }
      ]
    },
    "2": { "combinations": [ ... ] }
  },

  "num_offices_summary": [
    {
      "num_offices": 1,
      "top_combination_id": "k1_combo_1",
      "trip_p95": 72,
      "total_rent": 3000000,
      "hazard_avg": 65,
      "vs_previous": null
    },
    {
      "num_offices": 2,
      "top_combination_id": "k2_combo_1",
      "trip_p95": 45,
      "total_rent": 4800000,
      "hazard_avg": 70,
      "vs_previous": {"trip_p95_change_pct": -37.5, "rent_change_pct": 60.0}
    }
  ],

  "ranking": null,

  "explain_pack": { ... },
  "sensitivity": { ... },
  "notices": [ ... ]
}
```

### ranking（重み指定時のみ生成）
```json
"ranking": {
  "weights_normalized": {"access": 0.5, "financial": 0.3, "hazard": 0.2},
  "ranked_combinations": [
    {"combination_id": "k2_combo_1", "overall_score_0_100": 72.3, "rank": 1}
  ],
  "best_combination_id": "k2_combo_1"
}
```

---

## 5. 通勤悪化分布Notice

baseline がある場合、30分以上悪化する社員数を集計してNoticeで表示。
予測ではなく事実の集計。

---

## 6. CSV入力

### 社員データCSV
```csv
station_id,count,group
omiya,5,開発
yokohama,8,営業
```
- `group`列は任意
- 駅名（日本語）も受付 → station_master.json で駅IDに変換

### エンドポイント
`POST /parse-csv` — CSVを受け取り、`home_station_distribution` 形式に変換して返す

---

## 7. チーム分担

### 自分（バックエンド + 設計）
- v2バックエンド（マルチオフィス最適化、ハザード、ranking改修）
- APIスキーマ設計・テスト
- ハザードデータ収集（56駅分）

### 社内SEの友達（フロントエンド）
- v2フロントエンド（HTML/CSS/JS）
  - CSVアップロード + プレビューUI
  - 組み合わせ比較表・拠点数別サマリ表
  - 重みスライダー → ランキング表示
  - 2Dマップ（Canvas、zoom/pan対応）
  - Cesium 3Dビュー（駅柱、オフィスマーカー、Delta View）

### AI研究の友達（データ・AI）
- CSVパーサー + 駅名変換（POST /parse-csv）
  - 駅名の表記揺れ対応（オントロジーの知識活用）
- 駅ネットワークデータの拡充（ODPT API → 自動生成）
- AIによる explain_pack の自然言語生成（将来）

---

## 8. 実装変更箇所

### 新規
- `engine/combination.py` — 組み合わせ列挙 + 部署割り当て + フィルタ
- `data/station_hazard.json` — 56駅のハザードデータ
- `engine/csv_parser.py` — CSVパース + 駅名変換
- `routes/parse_csv.py` — POST /parse-csv
- `schemas/evaluation_report_v0.2.0.json`

### 変更
- `models/request.py` — group, num_offices, fixed_offices, fixed_assignment, budget
- `engine/pipeline.py` — 組み合わせループ、拠点数別サマリ
- `engine/ranking.py` — hazard_score(), ranking生成条件
- `engine/notices.py` — COMMUTE_WORSENING_DISTRIBUTION
- `engine/explain_pack.py` — combination単位

### 変更不要
- `routing.py`, `kpi.py`, `graph_loader.py`

---

## 9. テスト

### 既存（後方互換確認）
- test_determinism, test_monotonicity, test_unreachable

### 新規
1. test_combination — 組み合わせ列挙、固定制約、予算フィルタ
2. test_group_assignment — グループ割り当て、fixed_assignment
3. test_hazard — スコア範囲、overall_scoreへの影響
4. test_backward_compat — v1リクエストでv2正常動作
5. test_no_default_ranking — ranking_weights=null→ranking=null
6. test_csv_parser — パース、駅名→ID変換、group列任意

---

## 10. スコープ外

| 除外項目 | 理由 |
|---------|------|
| デフォルト重みランキング | 重みに根拠がない。ユーザーの価値観で決めるべき |
| 拠点数の自動提案 | 席数・設備が不明。データ提示に留める |
| 採用力・ブランドスコア | 定量化の根拠がない |
| CO2排出量 | 通勤時間と強く相関。独立した軸として弱い |
| 面積・席数 | 不動産仲介側のデータ |
| AI Parse（自動フォーマット認識） | 精度保証できない。固定フォーマットで実装 |
| 離職率推定 | 予測は信頼性を損なう。事実集計に留める |
| 地方移転（東京圏外） | 駅グラフが東京圏のみ。将来グラフ追加で対応 |
