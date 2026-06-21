# テストの既知の不足（メモ）

直近の変更で把握しているテスト・スキーマの未対応点。優先度がついたら埋める。

## 1. JSON Schema が新フィールドに未追従
`schemas/evaluation_report_v0.3.3.json` が以下を明記していない：
- `robustness[].capacity_headroom.per_office[].tight_estimate`
- `robustness[].capacity_headroom.warnings`
- `constraints_impact.after_min_capacity_filter`

いずれも `additionalProperties` 未設定のため検証は通るが、
「新フィールド追加のたびに Schema を更新する」方針（`tests/test_determinism.py` 参照）に未追従。

## 2. 推定定員ひっ迫警告の e2e テストが無い
`tight_estimate` / `warnings` は `_compute_capacity_headroom` の単体テストのみ
（`tests/test_logic.py::TestCapacityHeadroom`）。
`evaluate()` 全体を通して `robustness` に warnings が乗ることを確認する統合テストが無い。

## 3. 候補ゼロ診断（constraints_impact）の段分けテストが無い
`after_capacity / after_budget / after_min_capacity / after_commute` の各段が
正しく分かれることを検証するテストが無い。
- 今回 `after_min_capacity_filter` を追加し、min_total_capacity による脱落が
  通勤フィルタに誤帰属していたバグを修正した。
- ただしこの修正に対する回帰テストは未追加（要追加）。
