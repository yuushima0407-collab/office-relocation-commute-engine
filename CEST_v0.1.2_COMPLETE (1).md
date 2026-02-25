# CEST (City–Enterprise Scenario Toolkit)
**仕様書 v0.1.2 / 完全版 SSOT**
Last Updated: 2026-02-16

---

# README（外向け・5分で読める入口）

## これは何か

企業がオフィス移転・拠点再編を検討するとき、候補地ごとの**通勤負荷を定量比較**し、「誰がどれくらい辛いか」「どの働き方で緩和できるか」を**説明パックとして自動生成**するツール。

## なぜ作ったか

オフィス移転の意思決定で「通勤利便性」は重要な判断軸（CBRE日本オフィス戦略調査）。東京都はオフピーク通勤を継続推進しており、企業が出社頻度・時差調整を検討する機会が増えている。

既存の分析手段の限界：

```
不動産会社の無料分析：
→「平均通勤時間40分」の表を1枚もらうだけ
→ 誰が辛いか（分布）が見えない
→ 候補を変えるたびに再依頼が必要

Excel自力分析：
→ 2案・1回の比較なら十分
→ 候補が5案・働き方バリエーションが複数になると破綻
  （更新漏れ・計算ミス・フォーマット崩れ）
```

CESTの差別化：**反復検討 × 一貫性 × ミス耐性 × 説明パック自動生成**

## 誰が使うか

**一次ユーザー：企業の人事・総務（ワークプレイス担当）**

典型的な作業シーン：
```
上司から「来週の会議までに品川・渋谷・豊洲の3案を比較して」と言われる
→ 交通費データのCSVをCESTにアップロード
→ 3オフィスの情報を入力
→ 比較表・分布・トレードオフ文章が自動で出てくる
→ PPTに貼って完成
所要時間目標：30分以内
```

## アーキテクチャ概要

```
[入力]
交通費申請CSV → 居住駅の自動抽出・集計・マッチング確認
オフィス候補情報（最寄駅・ラストマイル・家賃）
現状の出社ポリシー

[バックエンド Python]
NetworkX Dijkstra → 居住駅→オフィス最寄駅の最短時間
KPI計算 → avg/p50/p95/閾値超/unreachable/coverage
ランキング → スコア計算（式固定・重み正規化）
説明パック → tradeoffs/if_you_prioritize/sensitivity（ルールベース自動生成）

[フロントエンド React + Cesium]
比較表（シナリオ横並び）
駅柱ビュー（高さ=人数・色=負荷帯）
Delta View（改善/悪化の分布）
重みスライダー
```

## バージョンロードマップ

| バージョン | 状態 | 内容 |
|-----------|------|------|
| **v0.1** | **本仕様** | コア比較エンジン＋説明パック＋Cesium可視化 |
| v0.2 | 計画中 | client_access軸・qualitative軸・targeted_quantile |
| v1.0 | 北極星 | Scope3 CO2・Schema後方互換固定 |

---

# Part 0: 担当分担（チーム向け）

## 分担の原則

CESTの設計思想（「計算できないものは出さない」「断言できないときは断言しない」）を理解した上で実装する必要がある部分を**あなたが担当**する。
ロジックが明確に定義されていて実装に専念できる部分をバックエンド・フロントエンド担当に振る。

## 担当一覧

### 🟦 私が実装
ver0.1ではフロント以外全部

### 🟩 AI担当
ver0.2以降の拡張から参加


### 🟥 フロントエンド担当
webフォルダの中すべて(フロントすべて)

# Part 1: Non-goals（v0.1ではやらない）

| 除外項目 | 理由 |
|---------|------|
| 離職率推定・採用難易度推定 | 前提パラメータが多すぎ・説明不能 |
| 混雑ストレス推定 | 時刻データ依存・現実データ取得困難 |
| 時差で何分短縮かの推定 | 時刻表依存 |
| 住所→駅変換 | 個人情報の粒度増加・変換精度保証困難 |
| 通勤費の（駅×オフィス）厳密計算 | v0.1はfinancial=家賃のみ |
| targeted_quantile（上位◯%配慮） | v0.2で検討 |
| client_access軸（取引先アクセス） | v0.2で検討 |
| qualitative軸（ブランド・採用力等） | v0.2で検討 |

---

# Part 2: プロダクト仕様（v0.1）

## 1. v0.1の完成定義

以下が全て動けばv0.1完成とする。

- 2〜5候補オフィスの比較（KPI全量・coverage含む）
- ランキング（重みスライダー・スコア式固定・正規化済み）
- 説明パック（tradeoffs/if_you_prioritize/sensitivity翻訳文）の自動生成
- Cesium：駅柱＋Delta Viewが最低1画面で動く
- 出力JSONがv0.1.2 Schemaに適合
- pytestテスト3本がパス

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| Home Station Distribution | 居住駅の集計（station_id × 人数。個人単位を扱わない） |
| Office Candidate | 候補拠点（最寄駅＋ラストマイル分＋家賃） |
| Trip Minutes | 片道所要分（rail_minutes + last_mile_minutes） |
| Round Trip Minutes | 往復所要分（Trip × 2） |
| Weekly Minutes | 週間通勤分（Round Trip × 週出社日数） |
| Scenario | (Office Candidate × As-Is Policy) の組み合わせ1つ |
| Baseline Scenario | delta計算の基準となるシナリオ（settings.baseline_office_idで指定） |
| Explain Pack | tradeoffs / if_you_prioritize / sensitivity の3点セット |
| quality_label | 値の根拠種別（computed / computed_simple / input_proxy） |

## 3. quality_labels（SSOT）

全ての数値に根拠を付ける。UIのExplainタブで必ず表示。

| ラベル | 意味 | v0.1での使用箇所 |
|-------|------|----------------|
| `computed` | CESTが計算した値。根拠として強い | KPI・スコア全般 |
| `computed_simple` | 簡易モデルで計算。注記必須 | エリア代表駅で計算した場合 |
| `input_proxy` | ユーザーが入力した値。CESTは計算していない | qualitative軸（v0.2） |

## 4. データ入力設計

### 4.1 なぜ交通費CSVを基本入力とするか

日本企業でほぼ確実に存在するデータが交通費申請データ。
「社員の居住駅を教えてください」は個人情報的に難しくても、
「交通費データのCSVください」は経理・人事から数分で出てくる。

交通費申請の典型的な構造：
```
社員ID, 氏名, 申請経路, 月額
1001, 田中太郎, 川崎→品川→渋谷, 13,640円
1002, 鈴木花子, 大宮→赤羽→池袋, 18,900円
```
**経路の先頭駅 = 居住地最寄り駅**として扱う。

### 4.2 入力フロー（3ステップ）

```
Step 1: CSVアップロード
  どのフォーマットでもOK（freee/SmartHR/moneyforward/自社Excel）
  カラム選択UI（「経路が入っているのはこの列」）→ フロントエンド担当

Step 2: 自動マッチング + 確認画面（必須）
  「川崎→品川→渋谷」→ 先頭を抽出 →「川崎」
  「川崎駅」「JR川崎」等の表記ゆれをファジーマッチ
  結果を一覧表示し、ユーザーが確認・修正してOKを押す
  マッチングできない駅は UNRESOLVED として明示
  UNRESOLVEDがある状態では計算実行不可

Step 3: 集計結果のプレビュー
  「川崎駅: 45人」「大宮駅: 30人」...
  ここで人数がおかしければCSVを修正してやり直し
```

> UIにstation_idやrouting_graphなどのエンジニア用語は一切出さない。内部に閉じる。

### 4.3 入力パターン（3種類）

| パターン | 対象 | 精度 | quality_label |
|---------|------|------|--------------|
| **パターン1（推奨）** 交通費CSV投入 | 既存データがある企業 | 高 | computed |
| **パターン2** エリア別人数を直接入力 | データがない・試したい | 低 | computed_simple |
| **パターン3** station_id × count CSV直接投入 | 自社集計済み | 高 | computed |

パターン2の画面イメージ：
```
大体どの方面に何人いますか？（概算でOK）

横浜・川崎方面 [  ] 人  → 代表駅：横浜
埼玉方面      [  ] 人  → 代表駅：大宮
千葉方面      [  ] 人  → 代表駅：千葉
23区内        [  ] 人  → 代表駅：新宿
その他・不明  [  ] 人

※ エリア代表駅で計算します
※ 精度は低くなります（Notice: AREA_PROXY_USED）
```

### 4.4 必須入力フィールド

```
居住駅分布（Home Station Distribution）:
  - station_id: string
  - count: integer（最低1）
  - segment: string | null（部署・職種・年齢帯など。任意）
  - office_days_per_week_override: number | null
    → その駅/セグメントだけ出社日数が違う場合（既存運用の反映）

候補オフィス（Office Candidates）: 2〜5件
  - office_id, name
  - nearest_station_id
  - last_mile_minutes（駅→オフィス徒歩/バス分。内訳推定しない・Fact入力）
  - lat / lon（Cesium表示用。なければnull）
  - rent_jpy_month（家賃。ない場合はnull → financial軸はnull）

現状ポリシー（Policy As-Is）:
  - office_days_per_week: 0〜5

設定（Settings）:
  - baseline_office_id: string | null
    → deltaの基準オフィス。nullなら office_candidates先頭を使う（SSOT）
  - thresholds_trip_minutes: デフォルト [60, 90]
  - percentiles: 固定 [50, 95]（v0.1は変更不可。変更はv0.2）
  - ranking_weights: access/financial/environmental（正規化はバックエンドで実施）
  - bench_trip_p95_minutes: デフォルト 90
  - bench_rent_jpy_month: デフォルト 10,000,000
  - routing.graph_id: デフォルト "tokyo_core_v1"（UIに出さない）
  - routing.transfer_penalty_minutes: v0.1は 0 のみサポート
    → 非0が入力された場合 Notice: TRANSFER_PENALTY_UNSUPPORTED（warning）を出して無視
```

### 4.5 Policyの適用優先順位（SSOT）

```
1. 駅/セグメントに office_days_per_week_override がある → それを使う
2. ない → policy_as_is.office_days_per_week を使う
```

**policy_applied.office_days_per_week の計算（SSOT）：**

```python
# 人数加重平均（overrideが混在する場合の代表値）
policy_applied.office_days_per_week = (
    Σ(count_i * applied_days_i) / population
)

# override_population_share（任意・UI表示用）
override_population_share = (
    Σ(count_i for i where override applied) / population
)
```

## 5. ルーティング設計【バックエンド担当】

### 5.1 何をするか・しないか

するもの：
- 駅ネットワーク（グラフ）上で最短所要分を計算
- 接続性の保証（繋がっていない駅を繋がっているように計算することを防ぐ）

しないもの：
- 時刻表・混雑・時間帯別ルーティング・車通勤の精密モデル

### 5.2 計算方法（SSOT）

```python
rail_minutes = NetworkX.dijkstra(
    graph,
    source=home_station_id,
    target=office.nearest_station_id
)
# 到達不能の場合 → None を返す（0で埋めない）

trip_minutes = rail_minutes + office.last_mile_minutes
round_trip_minutes = trip_minutes * 2
weekly_minutes = round_trip_minutes * office_days_per_week_applied
```

ライブラリ：**NetworkX**（Dijkstra自前実装禁止）

### 5.3 デフォルトグラフ

- `graph_id = "tokyo_core_v1"`: 主要駅セットをバンドル済み
- ユーザーはグラフを意識しない（UIに出さない）

### 5.4 Station Master（駅マスタ）

Cesiumの駅柱表示に緯度経度が必要。

```
Station Master（内部ファイル）:
  station_id → {name, lat, lon}

解決ルール（SSOT）:
  station_idが Station Master に存在する → lat/lon を使う
  存在しない → Notice: STATION_COORD_MISSING（info）
               Cesiumでその駅は非表示
```

### 5.5 unreachableの扱い（SSOT）

- rail_minutesがNone → **unreachable**
- unreachableは結果に必ず含める（count=0でも）
- **推定で埋めることは絶対にしない**
- unreachableが1件以上 → Notice: UNREACHABLE_EXISTS（warning）必須

## 6. KPI定義（SSOT・凍結）【バックエンド担当】

### 6.1 three_stats（共通型）

```
three_stats = { avg, p50, p95 }

null条件（SSOT）:
  population_reachable == 0 のとき全フィールドが null
  → Notice: NO_REACHABLE_POPULATION（error）を必ず出す
```

### 6.2 統計指標

各シナリオで以下を計算して返す。

| KPI | 定義 |
|-----|------|
| trip_minutes | 片道所要分の three_stats |
| round_trip_minutes | 往復所要分の three_stats |
| weekly_minutes | 週間通勤分の three_stats（Policy反映後） |

### 6.3 閾値超過

```
thresholds（settings.thresholds_trip_minutesに対応）:
  - trip_minutes: 閾値（片道分）
  - exceed_count: 超過人数
  - exceed_share: 超過割合（0〜1）
```

### 6.4 coverage_stats（SSOT）【バックエンド担当】

v3.5.5から吸収。「このデータで信頼できる計算ができているか」を示す。

```python
population_total = Σ count_i（全員）
population_reachable = Σ count_i（reachable=trueの駅のみ）
network_covered_ratio = population_reachable / population_total
# → 0.90未満で Notice: COVERAGE_LOW（warning）

quality_label:
  パターン1/3（CSV直接）→ computed
  パターン2（エリア代表）→ computed_simple
```

### 6.5 station_breakdown（SSOT）

```
駅ごとに:
  - station_id, count
  - reachable: boolean  ← v0.1.2追加（unreachable判定をUIが使いやすくする）
  - trip_minutes: number | null
    null条件: reachable=falseのとき
  - threshold_results: [{trip_minutes: 60, exceeds: boolean}, ...]
    unreachableのとき: 全て exceeds=false（推定しない）
  - delta_vs_baseline_trip_minutes: number | null
    null条件（SSOT）:
      - このシナリオがbaselineと同一
      - このシナリオまたはbaselineでreachable=false
```

### 6.6 baselineの決定ルール（SSOT）【あなたが実装】

```python
# baseline_office_idの解決
if settings.baseline_office_id is not None:
    if settings.baseline_office_id in [c.office_id for c in office_candidates]:
        baseline_office_id = settings.baseline_office_id
    else:
        # 指定されたoffice_idが候補にない
        baseline_office_id = office_candidates[0].office_id
        emit Notice: BASELINE_OFFICE_NOT_FOUND（warning）
else:
    baseline_office_id = office_candidates[0].office_id

# 出力のtop-levelに記録（実装ブレ防止）
output.baseline_scenario_id = scenario_id where office_id == baseline_office_id
```

## 7. ランキング（スコア式SSOT）

### 7.1 軸（v0.1）

| 軸 | v0.1 |
|----|------|
| access | 必須・スコア式固定 |
| financial | rent_jpy_monthがある場合のみ |
| environmental | v0.1はnull固定（v1.0でCO2追加） |

### 7.2 access_score（SSOT・凍結）【バックエンド担当】

主指標：**p95_trip_minutes（片道）**

理由：weekly_minutesは出社日数に依存するため「場所の比較」にならない。片道で統一することで純粋なオフィスの場所比較になる。

```python
bench_trip_p95_minutes = settings.bench_trip_p95_minutes  # デフォルト90

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

access_score = 100 * clamp(
    1 - (p95_trip_minutes / bench_trip_p95_minutes), 0, 1
)
# population_reachable == 0 → access_score = null
quality_label = "computed"
```

例：p95=45分 → 50点。p95=30分 → 67点。p95=90分超 → 0点。

### 7.3 financial_score（SSOT）

```python
bench_rent = settings.bench_rent_jpy_month  # デフォルト10,000,000

if rent_jpy_month is None:
    financial_score = null
    inputs_available = false
else:
    financial_score = 100 * clamp(
        1 - (rent_jpy_month / bench_rent), 0, 1
    )
    inputs_available = true
quality_label = "computed"
```

### 7.4 重み正規化（SSOT）

```python
weights = settings.ranking_weights  # {access, financial, environmental}
total = sum(weights.values())

if total == 0:
    # 全重みが0 → accessを1に強制
    normalized = {"access": 1.0, "financial": 0.0, "environmental": 0.0}
    emit Notice: WEIGHTS_ALL_ZERO_FALLBACK（warning）
else:
    normalized = {k: v / total for k, v in weights.items()}

overall_score = sum(
    normalized[axis] * score[axis]
    for axis in ["access", "financial", "environmental"]
    if score[axis] is not None
)
# overall_scoreは0〜100に収まることが保証される
```

### 7.5 best_scenario_idの条件（SSOT）【

```python
if sensitivity.robust == True:
    best_scenario_id = overall最大のscenario_id
else:
    best_scenario_id = null
    # 主役はexplain_packに移る
```

「断言できないときは断言しない」が設計原則。

## 8. 説明パック自動生成（CESTの核心）

### 8.1 なぜここが核心か

「誰が辛いか」の分布を出すだけなら、丁寧なExcelでもできる。
CESTの差別化は「比較 → トレードオフ文章 → 次に確認すべきこと」を毎回同じフォーマットで自動生成すること。

### 8.2 tradeoffs（テンプレート生成・SSOT）

対象：overall上位2シナリオを比較する。

```python
# Step 1: 上位2シナリオの差分を計算
A = overall 1位シナリオ
B = overall 2位シナリオ

candidates = []

# 差分候補1: p95_trip_minutes
delta_p95 = A.kpis.trip_minutes.p95 - B.kpis.trip_minutes.p95
candidates.append({
    "abs": abs(delta_p95),
    "text": f"{A.name}は{B.name}より p95(片道)が {abs(delta_p95):.0f}分 {'短い' if delta_p95 < 0 else '長い'}"
})

# 差分候補2: 90分超割合（thresholdsから取得）
delta_exceed = A_exceed_share_90 - B_exceed_share_90
candidates.append({
    "abs": abs(delta_exceed) * 100,
    "text": f"{A.name}は90分超の社員が {abs(delta_exceed)*100:.1f}pt {'少ない' if delta_exceed < 0 else '多い'}"
})

# 差分候補3: 家賃（両方rentがある場合のみ）
if A.rent and B.rent:
    delta_rent = A.rent - B.rent
    candidates.append({
        "abs": abs(delta_rent),
        "text": f"{A.name}は家賃が月{abs(delta_rent):,}円 {'安い' if delta_rent < 0 else '高い'}"
    })

# 差分候補4: 最も辛い駅（station_breakdownから）
worst_station = station_breakdown で delta_vs_baseline が最大の駅（Top1）
if worst_station:
    candidates.append({
        "abs": abs(worst_station.delta),
        "text": f"{worst_station.station_id}駅の{worst_station.count}人が、{A.name}では平均{abs(worst_station.delta):.0f}分{'改善' if worst_station.delta < 0 else '悪化'}"
    })

# Step 2: abs値の大きい順に上位2つを選んで出力
tradeoffs = [c["text"] for c in sorted(candidates, key=lambda x: -x["abs"])[:2]]
```

### 8.3 if_you_prioritize（SSOT）

```python
if_you_prioritize = {}

# access
if_you_prioritize["access"] = [
    scenario_id of max(access_score) across all scenarios
]

# financial（inputs_availableのシナリオのみ）
financial_available = [s for s in scenarios if s.axes.financial.inputs_available]
if financial_available:
    if_you_prioritize["financial"] = [
        scenario_id of max(financial_score) among financial_available
    ]
```

### 8.4 sensitivity（データ品質チェック）

**v0.1の感度分析は「入力データの不確実性チェック」として位置づける。**

揺らすパラメータ（v0.1は1種類のみ）：
```
last_mile_minutes を ±5分（全オフィス候補に同時適用）
バリエーション: {-5, 0, +5} × N候補の組み合わせ
```

```python
# flip_rateの計算
total_variants = 0
flip_count = 0
baseline_best = best_scenario_id  # ±0のとき

for variant in all_last_mile_variants:
    variant_best = compute_overall_winner(variant)
    total_variants += 1
    if variant_best != baseline_best:
        flip_count += 1

flip_rate = flip_count / total_variants
robust = flip_rate <= settings.robust_flip_rate_threshold  # デフォルト0.10
critical_assumption = "last_mile_minutes"  # v0.1は固定

# summary翻訳文（SSOT）
if robust:
    summary = "前提（駅→オフィス徒歩時間）を±5分変えても、1位は変わりません。"
else:
    summary = f"前提を±5分変えると、{flip_rate*100:.0f}%のケースで1位が変わります。結論は不安定です。"

# next_action（SSOT）
if robust:
    next_action = "そのまま会議に出せます。"
else:
    next_action = "各オフィス候補のラストマイル（徒歩/バス分）を実測または正確な値で入力してから再計算してください。"
```

## 9. Notices（透明性のため必須）【発火ルール定義】

`actionability`UIで「対応必要」「参考」を色分けできる。

### 9.1 Notice共通フォーマット

```json
{
  "level": "info | warning | error",
  "code": "NOTICE_CODE",
  "message": "人間が読む説明文",
  "action": "次にすべきこと（null可）",
  "actionability": "needs_action | informational | blocking"
}
```

### 9.2 Notice一覧（SSOT）

| コード | level | actionability | 発火条件 |
|-------|-------|--------------|---------|
| ROUTING_GRAPH_MISSING | error | blocking | グラフが提供されず計算不能 |
| NO_REACHABLE_POPULATION | error | blocking | population_reachable == 0 |
| STATION_ID_NOT_FOUND | warning | needs_action | 駅IDがグラフに存在しない |
| UNREACHABLE_EXISTS | warning | needs_action | unreachableが1件以上 |
| COVERAGE_LOW | warning | needs_action | network_covered_ratio < 0.90 |
| RENT_MISSING | info | informational | rent_jpy_monthがnull |
| SENSITIVITY_UNSTABLE | warning | needs_action | robust=false |
| AREA_PROXY_USED | warning | informational | エリア代表駅で計算した場合 |
| BASELINE_OFFICE_NOT_FOUND | warning | needs_action | baseline_office_idが候補に存在しない |
| WEIGHTS_ALL_ZERO_FALLBACK | warning | informational | 全重みが0でaccess=1に強制 |
| TRANSFER_PENALTY_UNSUPPORTED | warning | informational | transfer_penalty_minutesが非0 |
| STATION_COORD_MISSING | info | informational | 駅がStation Masterに存在しない |
| OVERRIDE_APPLIED | info | informational | office_days_per_week_overrideが使用された |

## 10. 可視化設計（Cesium）【フロントエンド担当】

### 10.1 設計原則

「分析のための可視化」ではなく「**会議で伝えるための可視化**」。
1画面で「どこが辛いか」「どう変わるか」が分かれば勝ち。

### 10.2 駅柱ビュー（Station Columns）

```
位置: Station Masterのlat/lon
高さ: count（人数）
色:
  reachable=false → グレー
  trip_minutes >= 90分 → 赤系
  trip_minutes 60〜90分 → 黄色系
  trip_minutes < 60分 → 青系
```

### 10.3 Delta View（差分ビュー）

```
delta_vs_baseline_trip_minutes > 0（悪化）→ 赤強調
delta_vs_baseline_trip_minutes < 0（改善）→ 青強調
delta_vs_baseline_trip_minutes = null → グレー（unreachable等）
```

### 10.4 やらないこと

通勤ルートの線（Line）を大量に描くことはしない。
理由：500人分の線は視覚的ノイズになる。駅柱だけで「誰がどこに住んでいて、どれくらい辛いか」は十分に伝わる。

---

# Part 3: テスト不変条件（pytest 3本）

カバレッジではなく「**システムとして守るべき不変条件**」のテスト。
何をテストするかの判断力が面接で問われる。

## Test 1: 決定論（Determinism）

```python
def test_same_input_same_output():
    """
    同じ入力を与えたとき、何回実行しても必ず同じ出力になること。
    ランダム性・非決定的な処理が混入していないことを保証する。

    なぜこれが重要か：
    「昨日と今日で結果が違う」は合意形成ツールとして致命的。
    経営会議で「前回と数字が違う」と言われたときに
    「同じ入力からは常に同じ結果」を保証できることが信頼の基盤。
    """
    input_data = load_fixture("demo_3candidates.json")

    result_1 = evaluate(input_data)
    result_2 = evaluate(input_data)

    assert result_1["results"] == result_2["results"]
    assert result_1["ranking"] == result_2["ranking"]
    assert result_1["sensitivity"] == result_2["sensitivity"]
```

## Test 2: unreachableで落ちない（Robustness）

```python
def test_unreachable_station_does_not_crash():
    """
    路線ネットワークに存在しない駅が入力に含まれても
    クラッシュせず、unreachableとして正しく報告されること。

    なぜこれが重要か：
    実際のデータには必ず想定外の駅が入る。
    「落ちること」が最悪の失敗。
    unreachableを0分として扱うことも同様に最悪（サイレントバグ）。
    """
    input_data = load_fixture("demo_3candidates.json")
    input_data["inputs"]["home_station_distribution"].append(
        {"station_id": "nonexistent_island_sta", "count": 5, "segment": None,
         "office_days_per_week_override": None}
    )

    result = evaluate(input_data)

    # クラッシュしない
    assert result is not None

    # unreachableに正しく報告される
    for scenario_result in result["results"]:
        unreachable_ids = [s["station_id"] for s in scenario_result["unreachable"]["stations"]]
        assert "nonexistent_island_sta" in unreachable_ids

        # 0分として混入していない
        for sb in scenario_result["station_breakdown"]:
            if sb["station_id"] == "nonexistent_island_sta":
                assert sb["reachable"] == False
                assert sb["trip_minutes"] is None

    # Noticeが出る
    notice_codes = [n["code"] for n in result["notices"]]
    assert "UNREACHABLE_EXISTS" in notice_codes
```

## Test 3: 出社頻度を下げると週間負荷が単調に改善（Monotonicity）

```python
def test_reducing_office_days_monotonically_improves_weekly_load():
    """
    他の条件が同じで出社日数だけを減らしたとき、
    weekly_minutesのp95が単調に改善されること。
    「週3より週2の方が通勤負荷が高い」はありえない。

    なぜこれが重要か：
    「働き方で緩和できるか」がCESTの核心機能の一つ。
    この単調性が崩れると、緩和策の提示が意味をなさない。
    weekly_minutes = round_trip × days の定義から自明だが、
    実装でoverrideや加重平均が絡むとバグりやすい。
    """
    from copy import deepcopy

    base_input = load_fixture("demo_3candidates.json")
    p95_weekly_by_days = {}

    for days in [5, 4, 3, 2, 1]:
        inp = deepcopy(base_input)
        inp["inputs"]["policy_as_is"]["office_days_per_week"] = days
        # overrideを全て除去（純粋にdays変化だけ見る）
        for dist in inp["inputs"]["home_station_distribution"]:
            dist["office_days_per_week_override"] = None

        result = evaluate(inp)
        reachable_result = result["results"][0]  # 最初のオフィス候補で比較
        p95_weekly_by_days[days] = reachable_result["kpis"]["weekly_minutes"]["p95"]

    # 日数が減るにつれてp95_weeklyも単調減少（または同値）
    for d in [4, 3, 2, 1]:
        assert p95_weekly_by_days[d] <= p95_weekly_by_days[d + 1], \
            f"週{d}日のp95weekly({p95_weekly_by_days[d]:.1f})が" \
            f"週{d+1}日({p95_weekly_by_days[d+1]:.1f})より大きい（単調性違反）"
```

---

# Part 4: JSON Schema Contract（v0.1.2 / SSOT）

実装者が「これだけ見れば入出力を壊さない」ための契約。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "cest://schemas/evaluation_report/v0.1.2",
  "title": "CEST Evaluation Report v0.1.2",
  "type": "object",
  "required": [
    "version", "generated_at",
    "baseline_scenario_id",
    "inputs", "results",
    "ranking", "explain_pack", "sensitivity",
    "notices"
  ],
  "properties": {
    "version": { "type": "string", "const": "v0.1.2" },
    "generated_at": { "type": "string", "format": "date-time" },

    "baseline_scenario_id": {
      "type": ["string", "null"],
      "description": "deltaの基準シナリオID。BASELINE_OFFICE_NOT_FOUNDのときnull"
    },

    "inputs": {
      "type": "object",
      "required": [
        "home_station_distribution", "office_candidates",
        "policy_as_is", "settings"
      ],
      "properties": {
        "home_station_distribution": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "object",
            "required": ["station_id", "count"],
            "properties": {
              "station_id": { "type": "string" },
              "count": { "type": "integer", "minimum": 1 },
              "segment": { "type": ["string", "null"] },
              "office_days_per_week_override": {
                "type": ["number", "null"],
                "minimum": 0, "maximum": 5
              }
            },
            "additionalProperties": false
          }
        },

        "office_candidates": {
          "type": "array",
          "minItems": 2, "maxItems": 5,
          "items": {
            "type": "object",
            "required": ["office_id", "name", "nearest_station_id", "last_mile_minutes"],
            "properties": {
              "office_id": { "type": "string" },
              "name": { "type": "string" },
              "nearest_station_id": { "type": "string" },
              "last_mile_minutes": { "type": "number", "minimum": 0, "maximum": 60 },
              "lat": { "type": ["number", "null"] },
              "lon": { "type": ["number", "null"] },
              "rent_jpy_month": { "type": ["integer", "null"], "minimum": 0 }
            },
            "additionalProperties": false
          }
        },

        "policy_as_is": {
          "type": "object",
          "required": ["office_days_per_week"],
          "properties": {
            "office_days_per_week": { "type": "number", "minimum": 0, "maximum": 5 }
          },
          "additionalProperties": false
        },

        "settings": {
          "type": "object",
          "required": [
            "baseline_office_id",
            "thresholds_trip_minutes",
            "ranking_weights",
            "bench_trip_p95_minutes",
            "bench_rent_jpy_month",
            "robust_flip_rate_threshold",
            "routing"
          ],
          "properties": {
            "baseline_office_id": {
              "type": ["string", "null"],
              "description": "nullなら office_candidates先頭を使う"
            },
            "thresholds_trip_minutes": {
              "type": "array", "minItems": 1,
              "items": { "type": "number", "minimum": 0 },
              "default": [60, 90]
            },
            "percentiles": {
              "type": "array",
              "const": [50, 95],
              "description": "v0.1は[50,95]固定。変更はv0.2以降"
            },
            "ranking_weights": { "$ref": "#/$defs/ranking_weights" },
            "bench_trip_p95_minutes": {
              "type": "number", "minimum": 1, "default": 90
            },
            "bench_rent_jpy_month": {
              "type": "number", "minimum": 1, "default": 10000000
            },
            "robust_flip_rate_threshold": {
              "type": "number", "minimum": 0, "maximum": 1, "default": 0.10
            },
            "routing": {
              "type": "object",
              "required": ["graph_id", "transfer_penalty_minutes"],
              "properties": {
                "graph_id": {
                  "type": ["string", "null"],
                  "description": "v0.1サポート: 'tokyo_core_v1'。UIに出さない"
                },
                "transfer_penalty_minutes": {
                  "type": "number", "minimum": 0, "maximum": 60, "default": 0,
                  "description": "v0.1は0のみ有効。非0はNotice出して無視"
                }
              },
              "additionalProperties": false
            }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false
    },

    "results": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": [
          "scenario_id", "office_id",
          "policy_applied", "kpis",
          "coverage", "station_breakdown", "unreachable"
        ],
        "properties": {
          "scenario_id": { "type": "string" },
          "office_id": { "type": "string" },

          "policy_applied": {
            "type": "object",
            "required": ["office_days_per_week", "override_population_share"],
            "properties": {
              "office_days_per_week": {
                "type": "number", "minimum": 0, "maximum": 5,
                "description": "人数加重平均。override混在時の代表値"
              },
              "override_population_share": {
                "type": "number", "minimum": 0, "maximum": 1,
                "description": "overrideが適用された人員の割合"
              }
            },
            "additionalProperties": false
          },

          "kpis": {
            "type": "object",
            "required": [
              "population", "population_reachable",
              "trip_minutes", "round_trip_minutes", "weekly_minutes",
              "thresholds"
            ],
            "properties": {
              "population": { "type": "integer", "minimum": 1 },
              "population_reachable": {
                "type": "integer", "minimum": 0,
                "description": "0のとき three_statsは全null・Notice: NO_REACHABLE_POPULATION"
              },
              "trip_minutes": { "$ref": "#/$defs/three_stats" },
              "round_trip_minutes": { "$ref": "#/$defs/three_stats" },
              "weekly_minutes": { "$ref": "#/$defs/three_stats" },
              "thresholds": {
                "type": "array",
                "items": {
                  "type": "object",
                  "required": ["trip_minutes", "exceed_count", "exceed_share"],
                  "properties": {
                    "trip_minutes": { "type": "number", "minimum": 0 },
                    "exceed_count": { "type": "integer", "minimum": 0 },
                    "exceed_share": { "type": "number", "minimum": 0, "maximum": 1 }
                  },
                  "additionalProperties": false
                }
              }
            },
            "additionalProperties": false
          },

          "coverage": {
            "type": "object",
            "required": ["network_covered_ratio", "quality_label"],
            "properties": {
              "network_covered_ratio": {
                "type": "number", "minimum": 0, "maximum": 1,
                "description": "population_reachable / population"
              },
              "quality_label": {
                "type": "string",
                "enum": ["computed", "computed_simple"]
              }
            },
            "additionalProperties": false
          },

          "station_breakdown": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["station_id", "count", "reachable", "trip_minutes", "threshold_results"],
              "properties": {
                "station_id": { "type": "string" },
                "count": { "type": "integer", "minimum": 1 },
                "reachable": {
                  "type": "boolean",
                  "description": "falseのとき trip_minutesはnull"
                },
                "trip_minutes": {
                  "type": ["number", "null"],
                  "minimum": 0,
                  "description": "null条件: reachable=false"
                },
                "threshold_results": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "required": ["trip_minutes", "exceeds"],
                    "properties": {
                      "trip_minutes": { "type": "number", "minimum": 0 },
                      "exceeds": {
                        "type": "boolean",
                        "description": "unreachableのとき常にfalse"
                      }
                    },
                    "additionalProperties": false
                  }
                },
                "delta_vs_baseline_trip_minutes": {
                  "type": ["number", "null"],
                  "description": "null条件: baselineと同一 / どちらかがreachable=false"
                }
              },
              "additionalProperties": false
            }
          },

          "unreachable": {
            "type": "object",
            "required": ["count", "stations"],
            "properties": {
              "count": { "type": "integer", "minimum": 0 },
              "stations": {
                "type": "array",
                "items": {
                  "type": "object",
                  "required": ["station_id", "count"],
                  "properties": {
                    "station_id": { "type": "string" },
                    "count": { "type": "integer", "minimum": 1 }
                  },
                  "additionalProperties": false
                }
              }
            },
            "additionalProperties": false
          }
        },
        "additionalProperties": false
      }
    },

    "ranking": {
      "type": "object",
      "required": ["weights_normalized", "axes", "overall", "best_scenario_id"],
      "properties": {
        "weights_normalized": {
          "$ref": "#/$defs/ranking_weights",
          "description": "バックエンドで正規化済み（合計=1）"
        },
        "axes": {
          "type": "object",
          "required": ["access", "financial", "environmental"],
          "properties": {
            "access": { "$ref": "#/$defs/axis_scores" },
            "financial": { "$ref": "#/$defs/axis_scores" },
            "environmental": { "$ref": "#/$defs/axis_scores" }
          },
          "additionalProperties": false
        },
        "overall": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["scenario_id", "overall_score_0_100"],
            "properties": {
              "scenario_id": { "type": "string" },
              "overall_score_0_100": {
                "type": "number", "minimum": 0, "maximum": 100
              }
            },
            "additionalProperties": false
          }
        },
        "best_scenario_id": {
          "type": ["string", "null"],
          "description": "sensitivity.robust=trueのときのみ値を入れる"
        }
      },
      "additionalProperties": false
    },

    "explain_pack": {
      "type": "object",
      "required": ["tradeoffs", "if_you_prioritize"],
      "properties": {
        "tradeoffs": {
          "type": "array",
          "maxItems": 2,
          "items": { "type": "string" },
          "description": "ルールベース自動生成。最大2行"
        },
        "if_you_prioritize": {
          "type": "object",
          "properties": {
            "access": { "type": "array", "items": { "type": "string" } },
            "financial": { "type": "array", "items": { "type": "string" } }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false
    },

    "sensitivity": {
      "type": "object",
      "required": [
        "robust", "flip_rate",
        "critical_assumption", "summary", "next_action",
        "variants"
      ],
      "properties": {
        "robust": { "type": "boolean" },
        "flip_rate": { "type": "number", "minimum": 0, "maximum": 1 },
        "critical_assumption": {
          "type": "string",
          "enum": ["last_mile_minutes"],
          "description": "v0.1は固定"
        },
        "summary": { "type": "string", "description": "自動生成翻訳文" },
        "next_action": { "type": "string", "description": "自動生成次アクション" },
        "variants": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["variant_id", "assumptions", "best_scenario_id"],
            "properties": {
              "variant_id": { "type": "string" },
              "assumptions": { "type": "object", "additionalProperties": true },
              "best_scenario_id": { "type": ["string", "null"] }
            },
            "additionalProperties": false
          }
        }
      },
      "additionalProperties": false
    },

    "notices": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["level", "code", "message", "actionability"],
        "properties": {
          "level": { "type": "string", "enum": ["info", "warning", "error"] },
          "code": { "type": "string" },
          "message": { "type": "string" },
          "action": { "type": ["string", "null"] },
          "actionability": {
            "type": "string",
            "enum": ["needs_action", "informational", "blocking"]
          }
        },
        "additionalProperties": false
      }
    }
  },

  "$defs": {
    "three_stats": {
      "type": "object",
      "required": ["avg", "p50", "p95"],
      "properties": {
        "avg": { "type": ["number", "null"], "minimum": 0 },
        "p50": { "type": ["number", "null"], "minimum": 0 },
        "p95": { "type": ["number", "null"], "minimum": 0 }
      },
      "description": "population_reachable==0のとき全フィールドがnull",
      "additionalProperties": false
    },
    "ranking_weights": {
      "type": "object",
      "required": ["access", "financial", "environmental"],
      "properties": {
        "access": { "type": "number", "minimum": 0, "maximum": 1 },
        "financial": { "type": "number", "minimum": 0, "maximum": 1 },
        "environmental": { "type": "number", "minimum": 0, "maximum": 1 }
      },
      "additionalProperties": false
    },
    "axis_scores": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["scenario_id", "score_0_100", "inputs_available", "quality_label"],
        "properties": {
          "scenario_id": { "type": "string" },
          "score_0_100": {
            "type": ["number", "null"],
            "minimum": 0, "maximum": 100
          },
          "inputs_available": { "type": "boolean" },
          "quality_label": {
            "type": "string",
            "enum": ["computed", "computed_simple", "input_proxy"]
          }
        },
        "additionalProperties": false
      }
    }
  },

  "additionalProperties": false
}
```

---

# Part 5: ロードマップ（v0.2 / v1.0）

## v0.2（v0.1で価値確認後に着手）

### client_access軸（取引先アクセス）

```
入力追加:
  office_candidates[*].client_access_stations:
    [{station_id: "shinjuku", label: "主要顧客A"}]

計算:
  オフィス最寄駅→取引先駅の所要分（既存routingエンジンで計算可能）

スコア:
  bench_client_trip_p95_minutes（設定可）を基準に正規化

quality_label: computed
```

### qualitative軸（ユーザー入力スコア）

```
入力追加:
  office_candidates[*].qualitative_scores:
    [{label: "採用力", score: 75}, {label: "ブランド", score: 80}]

スコア:
  ユーザーが入力した値をそのまま使う

quality_label: input_proxy（CESTは計算しない・ユーザーの判断）
```

`input_proxy`ラベルによって「この数字はCESTが計算したものではなく、あなたが判断した値です」をUIで明示できる。

### targeted_quantile（配慮シミュレーション）

```
「通勤負荷が重い層（上位◯%）の出社日数を別設定にする」
デフォルトOFF・Advanced扱い
v0.1を見て実装するか決める
```

### percentiles可変対応

```
v0.1は[50, 95]固定
v0.2でユーザーが設定できるようにする
three_statsを可変percentile出力に変更
```

## v1.0

```
Scope3 CO2（通勤由来）をFact KPIとして追加
  - 距離ベースのCO2推計
  - 円換算はしない
  - environmental軸が実際に使えるようになる

Schema後方互換固定
  - v0.xで変化してきた契約を正式にLock
  - 外部連携・再利用を想定
```

---

# Part 6: 設計判断の記録


## A. なぜ離職推定を削除したか

前バージョンでは`commute_sensitivity_factor=1.3`等のパラメータで離職影響を推定していた。

削除理由：
- パラメータの根拠が「仮定」で、説明できない
- 「なぜ1.3？」に答えられないと計算結果全体の信頼性が崩れる
- 「離職◯◯人」という数字が一人歩きして責任問題になる

代替設計：
- 通勤時間の分布（Fact）を出して「判断はユーザーに委ねる」
- 「誰が辛いか」を見える化すれば、離職リスクはユーザー自身が判断できる

## B. なぜaccess_scoreをweeklyではなくtripベースにしたか

`weekly_minutes = trip × 2 × 出社日数`

出社日数が変わるとweeklyが変わる。
「週3のオフィス案」と「週5のオフィス案」を比べるとき、weeklyベースのスコアは「場所の良さ」でなく「出社日数の少なさ」を測ってしまう。

tripベースにすることで「オフィスの場所を純粋に比較」できる。

## C. なぜbest_scenario_idをrobust=trueのときだけ出すか

`sensitivity.robust=false`のとき（前提が変わると結論も変わる場合）、「◯◯が最適です」と断言するのは不誠実。

ユーザーに「データの確認が必要」と伝えた上で、tradeoffsとif_you_prioritizeを主役にする方が実務的に役立つ。

「断言できないときは断言しない」を設計に組み込む。

## D. なぜ感度分析をlast_mileだけに絞ったか

揺らせるパラメータは複数ある（居住駅分布・家賃・グラフ構造等）。全部揺らすと計算量が爆発し「何が重要か」がユーザーに伝わらない。

last_mile_minutesだけにした理由：
- 「徒歩10分と書いたけど実際は15分だった」が最も起きやすいデータミス
- 全候補に同時適用するため「相対的な優劣の変化」を測れる
- ユーザーへのnext_actionが明確（「実測してください」）

## E. なぜqualitative軸をユーザー入力スコアにしたか

採用力・ブランディング・面積への満足度は業種・企業戦略によって全然違う。汎用的な計算式が作れない。

だからCESTは計算しない。ユーザーが自分の判断で点数を入れて、他の軸と同じ重みスライダーで比較できる設計にした。

`input_proxy`ラベルによって「この数字はCESTが計算したものではない」をUIで明示することで、誠実性を担保する。

## F. なぜtradeoffsに「最悪駅のTop1」を入れるか

「p95が◯分改善」という数字より「川崎駅の35人が20分改善」の方が、経営会議で具体性を持って伝わる。

station_breakdownのdeltaから最大の変化があった駅を抽出することで、自動生成でも「誰が・どれくらい・どう変わるか」を表現できる。

---

# Changelog

## v0.1.2（本仕様）
**P0修正（実装が割れる・バグる問題）**
- station_breakdown.trip_minutes を `["number","null"]` に変更
- station_breakdown に `reachable: boolean` を追加
- threshold_results: unreachable時は全て exceeds=false と明記
- three_stats の avg/p50/p95 を `["number","null"]` に変更
- kpis に `population_reachable` を追加
- Notice: NO_REACHABLE_POPULATION を追加
- settings に `baseline_office_id` を追加（deltaのSSOT化）
- 出力 top-level に `baseline_scenario_id` を追加
- BASELINE_OFFICE_NOT_FOUND Notice を追加
- policy_applied.office_days_per_week を人数加重平均とSSOT化
- policy_applied に `override_population_share` を追加
- ranking に `weights_normalized`（正規化済み）を追加
- WEIGHTS_ALL_ZERO_FALLBACK Notice を追加
- settings.percentiles を const [50,95] に凍結

**前バージョンからの吸収**
- quality_label を axis_scores に追加（computed/computed_simple/input_proxy）
- Notice に `actionability` を追加（needs_action/informational/blocking）
- coverage（network_covered_ratio）をresultsに追加
- COVERAGE_LOW Notice を追加

**設計改善**
- access_score の基準をweeklyからtrip（片道）に変更（出社日数の混入防止）
- tradeoffsに「最悪駅Top1」の言及を追加
- transfer_penalty_minutes: v0.1は0のみサポートとSSOT化
- TRANSFER_PENALTY_UNSUPPORTED Notice を追加
- Station Masterによる駅座標解決をSSOT化
- STATION_COORD_MISSING Notice を追加
- 担当分担（Part 0）を追加
- 設計判断の記録（Part 6）を追加

## v0.1.1
- ユーザー像・典型シーンをSection 0として追加
- 交通費CSVを基本入力として設計（3パターン対応）
- 確認ステップ（マッチング承認）を必須化

## v0.1.0
- 離職推定・混雑ストレス推定を削除
- Non-goalsを明文化
- JSON Schema初版
- sensitivity必須化
