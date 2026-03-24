# CEST AWS アーキテクチャ設計書

**作成者**: PM
**対象バージョン**: CEST v0.3.x
**最終更新**: 2026-02-28

---

## 1. システム概要

CEST（Commute Evaluation & Simulation Tool）は、オフィス配置の意思決定支援ツール。
フロントエンド（静的ファイル）とバックエンド（Python API）の2層構成。
コードをpushするだけで自動デプロイされるCI/CDパイプラインを持つ。

---

## 2. アーキテクチャ構成図

```
[ 開発者 ]
    │ git push (main ブランチ)
    ▼
┌─────────────────────────────────────────────────┐
│  GitHub + GitHub Actions (CI/CD)                │
│                                                 │
│  1. pytest 実行  →  失敗なら停止               │
│  2. cest/web/ を S3 に自動アップロード          │
│  3. CloudFront キャッシュを自動削除             │
│  4. Lambda コードを自動更新                     │
└──────┬──────────────────────────────────────────┘
       │ 自動デプロイ完了
       ▼
[ ユーザーブラウザ ]
       │ HTTPS
       ▼
┌──────────────────────────────────────────┐
│  CloudFront (CDN)                        │
│  - HTTPS 終端                            │
│  - 静的ファイルのキャッシュ・配信         │
└────────────┬─────────────────────────────┘
             │                  │ /evaluate
             │ 静的ファイル      │ /parse-csv
             ▼                  ▼
┌────────────────┐   ┌──────────────────────┐
│  S3 Bucket     │   │  API Gateway         │
│  (非公開)      │   │  (HTTP API)          │
│                │   └──────────┬───────────┘
│  index.html    │              │
│  app.js        │              ▼
│  style.css     │   ┌──────────────────────┐
│  demo_         │   │  Lambda Function     │
│  response.json │   │  (Python 3.11)       │
│  station_      │   │                      │
│  master.json   │   │  FastAPI + Mangum    │
│  tokyo_core_   │   │  networkx            │
│  v1.json       │   │  pydantic            │
└────────────────┘   └──────────────────────┘
```

---

## 3. 各コンポーネントの役割と選定理由

### 3-1. GitHub Actions（CI/CDパイプライン）

| 項目 | 内容 |
|---|---|
| トリガー | `main` ブランチへの push |
| ステップ | ① テスト → ② フロントデプロイ → ③ キャッシュ削除 → ④ バックエンドデプロイ |
| 認証情報 | AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY を GitHub Secrets に登録 |
| 選定理由 | GitHubに標準搭載・無料。手動デプロイのミスをなくす |
| 月額コスト | **無料**（パブリックリポジトリまたは月2000分まで） |

> **CI/CDを導入した理由**
> 手動デプロイは「古いファイルが残る」「手順ミス」「誰がいつデプロイしたか不明」という問題が起きる。
> mainへのpushを唯一のリリーストリガーにすることで、デプロイの一貫性と追跡可能性を確保する。

### 3-2. S3（静的ファイル置き場）

| 項目 | 内容 |
|---|---|
| 用途 | HTML/CSS/JS/JSONファイルの保管 |
| 公開設定 | **バケット自体は非公開**。CloudFront経由でのみアクセス |
| 選定理由 | サーバー不要・高可用性・無料枠で十分 |
| 月額コスト | ~$0（無料枠: 5GB, GET2万回/月） |

### 3-3. CloudFront（CDN・配信）

| 項目 | 内容 |
|---|---|
| 用途 | S3への安全なアクセス窓口 + HTTPS + キャッシュ |
| OAC設定 | S3への直接アクセスを禁止し、CloudFront経由のみ許可 |
| キャッシュ無効化 | デプロイ時に GitHub Actions が自動で `/*` を Invalidation |
| 選定理由 | HTTPSが自動・無料。S3を直接公開するよりセキュア |
| 月額コスト | **永久無料**（1TB転送/月まで） |

> **EC2やAmplifyではなくCloudFront+S3にした理由**
> サーバー維持コストゼロ。就活ポートフォリオの期間中は特にメンテナンス不要で動き続ける。

### 3-4. API Gateway（HTTPエンドポイント）

| 項目 | 内容 |
|---|---|
| 用途 | `/evaluate` `/parse-csv` `/parse-csv/upload` のHTTPエンドポイント |
| 種別 | **HTTP API**（REST APIより安く、シンプル） |
| 選定理由 | Lambdaの前段として必要。HTTP APIはREST APIの約70%安い |
| 月額コスト | ~$0（開設12ヶ月無料。以降は100万リクエスト=$1） |

### 3-5. Lambda（バックエンド実行環境）

| 項目 | 内容 |
|---|---|
| 用途 | FastAPI アプリケーションの実行 |
| ランタイム | Python 3.11 |
| アダプター | **Mangum**（FastAPIをLambdaで動かすための薄いラッパー） |
| メモリ | 512MB（networkxのグラフ計算に十分） |
| タイムアウト | 30秒 |
| 選定理由 | サーバー管理不要。トラフィックゼロ時は課金なし |
| 月額コスト | **永久無料**（100万リクエスト/月まで） |

> **EC2ではなくLambdaにした理由**
> EC2 t2.microは12ヶ月後に課金開始（~$10/月）。Lambdaは永久無料枠あり。
> CESはリクエスト数が少ない用途なのでLambdaが最適。

---

## 4. CI/CDパイプライン詳細

### ワークフローファイルの場所

```
.github/
└── workflows/
    └── deploy.yml
```

### ワークフローの流れ

```
git push to main
       │
       ▼
  ┌─────────┐
  │  Test   │  pytest cest/tests/
  └────┬────┘
       │ 成功のみ続行（失敗なら通知して停止）
       ▼
  ┌──────────────────┐
  │  Deploy Frontend │  aws s3 sync cest/web/ s3://バケット名/
  └────────┬─────────┘  --delete（削除ファイルも反映）
           │
           ▼
  ┌───────────────────────┐
  │  Invalidate CloudFront│  aws cloudfront create-invalidation --paths "/*"
  └────────┬──────────────┘  （キャッシュをクリアして最新版を即時配信）
           │
           ▼
  ┌──────────────────────┐
  │  Deploy Backend      │  Lambda関数コードを更新
  └──────────────────────┘
```

### GitHub Secrets に登録するもの

| Secret名 | 内容 |
|---|---|
| `AWS_ACCESS_KEY_ID` | AWSのIAMユーザーのアクセスキー |
| `AWS_SECRET_ACCESS_KEY` | AWSのIAMユーザーのシークレットキー |
| `AWS_REGION` | `ap-northeast-1`（東京） |
| `S3_BUCKET_NAME` | 作成したS3バケット名 |
| `CLOUDFRONT_DISTRIBUTION_ID` | CloudFrontのディストリビューションID |
| `LAMBDA_FUNCTION_NAME` | Lambda関数名 |

---

## 5. デプロイ対象ファイル

### フロントエンド（S3にアップロード）

```
cest/web/
├── index.html
├── app.js
├── style.css
├── demo_response.json
├── station_master.json
└── tokyo_core_v1.json
```

### バックエンド（Lambdaにデプロイ）

```
cest/src/
└── cest/          ← パッケージ全体

依存ライブラリ（Lambdaにバンドル）:
- fastapi
- pydantic
- networkx
- jsonschema
- mangum        ← 追加が必要（現在pyproject.tomlに未記載）
※ uvicornはLambdaでは不要
```

---

## 6. フロントエンドの API 向き先切り替え

```
デモモード（API不要）: demo_response.json を直接読む
本番モード: API Gateway の URL に向ける
```

`app.js` 先頭付近の `API_BASE_URL` を Lambda デプロイ後の URL に変更する。

---

## 7. セキュリティ要件

| 要件 | 対応 |
|---|---|
| 通信の暗号化 | CloudFront が HTTPS を提供。S3直接アクセス禁止 |
| 認証 | 不要（社内デモ・ポートフォリオ用途のため） |
| CORS | `main.py` で `allow_origins=["CloudFrontのURL"]` に絞る |
| Lambda の権限 | 最小権限。IAM Role は Lambda 基本実行権限のみ |
| AWS認証情報 | コードに直書き禁止。GitHub Secrets 経由でのみ使用 |

---

## 8. コスト試算

| サービス | 12ヶ月以内 | 12ヶ月以降 |
|---|---|---|
| S3 + CloudFront | 無料 | **無料** |
| Lambda | 無料 | **無料** |
| API Gateway | 無料 | ~$0〜$1/月 |
| GitHub Actions | 無料 | **無料** |
| **合計** | **$0** | **~$0〜$1/月** |

> 就活が終わったらリソースを削除すればコスト$0。

---

## 9. 実装タスク（エンジニア向け）

### Phase 1: フロントエンド + CI/CD

- [ ] AWS IAMユーザー作成（S3・CloudFront・Lambda操作権限）
- [ ] S3バケット作成（パブリックアクセスブロック有効）
- [ ] CloudFrontディストリビューション作成（OAC設定）
- [ ] `cest/web/` 以下を S3 に初回アップロード
- [ ] CloudFront URL で `index.html` が表示されることを確認
- [ ] デモモードが動作することを確認
- [ ] `.github/workflows/deploy.yml` を作成
- [ ] GitHub Secrets に AWS認証情報を登録
- [ ] テスト用のダミーコミットで GitHub Actions が動くことを確認

### Phase 2: バックエンド追加

- [ ] `pyproject.toml` に `mangum>=0.17.0` を追加
- [ ] `cest/src/cest/main.py` に Mangum ハンドラを追加（3行程度）
- [ ] Lambda 関数作成（Python 3.11, 512MB, 30秒タイムアウト）
- [ ] API Gateway HTTP API 作成 → Lambda に接続
- [ ] `app.js` の `API_BASE_URL` を API Gateway の URL に更新
- [ ] `allow_origins` を CloudFrontのURLに絞る
- [ ] `deploy.yml` にバックエンドデプロイのステップを追加
- [ ] `/evaluate` エンドポイントが動作することを確認

---

## 10. 将来拡張（今回のスコープ外）

- カスタムドメイン（Route 53 + ACM）
- ログ監視・アラート（CloudWatch）
- PRごとのプレビュー環境
