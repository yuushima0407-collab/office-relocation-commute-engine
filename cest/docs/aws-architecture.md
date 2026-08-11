# CEST AWS アーキテクチャ設計書（v0.3.3 改訂版）

**作成者**: 島田ゆうき
**対象バージョン**: CEST v0.3.3 / v0.4
**最終更新**: 2026-08-11
**ドメイン**: `yuki-shimada.dev`

---

## 0. このドキュメントについて

本ドキュメントは CEST のインフラ構成・設計判断を記録した設計書です。  
Phase ごとに「何を選んだか・なぜ選んだか・どう実装したか」を残しています。

### 現状（v0.3.3 時点）

| 項目 | 状態 |
|---|---|
| Phase 1（S3 + CloudFront） | ✅ 完了 — CloudShell 経由でセットアップ |
| Phase 1.5（Lambda + API Gateway） | ✅ 完了 → その後 Phase 3b で Container Image に移行 |
| Phase 2（独自ドメイン） | ⏳ 計画中 — Route 53 + ACM |
| Phase 3a（GitHub Actions CI/CD） | ✅ 完了 — OIDC 認証ベース（2026-08-11） |
| Phase 3b（Container Image 化） | ✅ 完了 — ECR + Lambda Container（Phase 3aと同時実施、2026-08-11） |
| Phase 4（Bedrock 統合） | ⏳ 計画中 — v0.4 機能 |

### 既に終わった設計判断（要約）

- **Lambda + API Gateway HTTP API**：常時稼働コストゼロ＋HTTP APIはRESTより約70%安い
- **S3 + CloudFront（OAC）**：S3を直接公開せず CloudFront 経由のみアクセス可能に
- **Mangum**：FastAPI（ASGI）を Lambda イベントに橋渡し、コード変更を最小化
- **zip デプロイから着手**：説明会前の確実性優先。Container Image 化は後段
- **EC2 + ELB の3層構成は採用せず**：常時起動コスト・運用負荷の観点でサーバーレスを選択
- **API Gateway は HTTP API を選択（REST API ではなく）**：必要機能は揃いつつコストが約70%安い

### 残タスクの方針

- **観測性**：CloudWatch Dashboard / X-Ray 導入で Lambda の遅延・エラー率を可視化（未着手）
- **Bedrock**：v0.4 で自然言語Q&A機能。同一AWS内で IAM 認可、外部API より運用が安全（未着手）
- **独自ドメイン（Phase 2）**：Route 53 + ACM。現状 CloudFront はデフォルトドメイン(`*.cloudfront.net`)のまま運用中

CI/CD自動化とContainer Image化はPhase 3a/3bとして完了済み（詳細は下記）。

---

## 1. 設計判断サマリ

| 項目 | 決定 | 理由 |
|---|---|---|
| 用途 | 公開デモURL付きの個人プロジェクト | URLを叩いて即動作確認できる状態を維持 |
| 予算 | 月数百円以内（実測 月170円程度） | サーバーレス前提、固定費を持たない |
| 認証 | なし | デモ用のオープン公開。代わりに後段でレート制限を検討 |
| ドメイン | 独自ドメイン `yuki-shimada.dev` | HTTPS強制（HSTSプリロード）でセキュリティ要件を満たす |
| Lambda 形式 | 段階的: zip → Container Image | 初期は zip で立ち上げ、依存サイズが増えたら Container 化 |
| CI/CD | 段階的: 手動 → GitHub Actions | 初期は確実性、安定後に自動化 |
| 監視 | CloudWatch Alarms（$1超で通知）| 個人プロジェクトでも事故防止のためコスト監視は最低限実装 |
| Bedrock（v0.4）| v0.3.x 安定後に着手 | 機能の段階的リリースを優先 |

---

## 2. Phase 分割

| Phase | 内容 | 工数 | 状態 |
|---|---|---|---|
| **1** | フロント公開（S3+CloudFront） | 5〜7h | ✅ 完了 |
| **1.5** | zip Lambda + API Gateway（CloudShell 経由） | 3〜5h | ✅ 完了（Phase 3bでContainer Imageに移行） |
| **2** | 独自ドメイン（Route53+ACM） | 3〜5h | ⏳ 予定 |
| **3a** | GitHub Actions 自動CI/CD | 3〜5h | ✅ 完了 |
| **3b** | zip → Container Image 移行 | 5〜8h | ✅ 完了（3aと同時実施） |
| **4** | Bedrock 統合（v0.4 機能） | 5〜10h | ⏳ 予定 |

**合計工数**: 24〜40h

---

## 3. 最終構成図（Phase 4 完成形）

```
                          [ ユーザーブラウザ ]
                                  │ HTTPS
                                  ▼
                  ┌─────────────────────────────┐
                  │  Route 53                   │
                  │  yuki-shimada.dev           │
                  └─────────────┬───────────────┘
                                │
                                ▼
                  ┌─────────────────────────────┐
                  │  CloudFront (CDN)           │
                  │  - HTTPS 終端 (ACM証明書)    │
                  │  - HTTPS強制 (.devポリシー)  │
                  │  - 静的ファイルキャッシュ      │
                  └────────┬──────────┬─────────┘
                           │          │ /evaluate
                           │ 静的      │ /ask     ← v0.4 追加
                  ┌──────────────┐    │
                  │  S3 Bucket   │    ▼
                  │  (非公開・OAC)│    ┌──────────────────┐
                  │              │    │ API Gateway      │
                  │ index.html   │    │ HTTP API         │
                  │ samples/     │    └─────────┬────────┘
                  └──────────────┘              │
                                                ▼
                                    ┌────────────────────────┐
                                    │ Lambda Function        │
                                    │ Python 3.11            │
                                    │ FastAPI + Mangum       │
                                    │ + boto3 (Bedrock)      │
                                    └─────────┬──────────────┘
                                              │ /ask の時のみ
                                              ▼
                                    ┌────────────────────────┐
                                    │ Amazon Bedrock         │
                                    │ Claude 3 Haiku         │
                                    └────────────────────────┘

[ GitHub: main ]
        │ git push
        ▼
[ GitHub Actions（OIDC） ] → pytest → docker build/push(ECR) → terraform apply(Lambda更新)
        → station_master.json同期 → S3 sync → CloudFront Invalidation
```

---

## 4. Phase ごとの方針

### Phase 1: フロント公開（S3 + CloudFront）— ✅ 完了

**目的**: 公開 URL からブラウザで CEST を動作確認できる状態にする

**実施内容（要点）**:
- S3 はパブリックアクセスブロック有効で運用、CloudFront 経由でのみ公開
- CloudFront に OAC（Origin Access Control）を設定、S3 への直接アクセスを禁止
- バケットポリシーは CloudFront 用に手動で貼り付け（OAC を作っても自動更新されない仕様）

**運用上の注意**:
- CloudFront キャッシュは反映に 5〜10分かかる。デプロイ後に Invalidation を打つか、待つ判断が必要

---

### Phase 1.5: zip Lambda + API Gateway — ✅ 完了

**目的**: フロントから API を叩いて実データで計算が走る状態にする

**実施内容（要点）**:
- AWS CloudShell（Cloud9 は 2024-07 で新規受付終了したため代替）で Python 3.11 + 依存パッケージを bundle した zip を作成
- zip 作業は CloudShell の `/tmp` 配下（ホームは 1GB 制限のため）
- zip サイズが 50MB を超えるため、直接アップロードではなく S3 経由で Lambda にアップロード
- Mangum で FastAPI（ASGI）を Lambda イベントに橋渡し
- API Gateway HTTP API を Lambda に統合、CORS は当面 `*` 運用（Phase 2 でドメインに絞る）

**ビルド環境に CloudShell を選んだ理由と脱却条件**:

zip 作成環境の候補は次の 4 つを比較した。

| 候補 | 採否 | 評価 |
|---|---|---|
| ローカル Windows で `pip install` → zip | ❌ | Windows でビルドしたネイティブ拡張（`pydantic-core` 等）は Amazon Linux で動かない（実際に Phase 1.5 で踏んだ） |
| ローカル Docker（`public.ecr.aws/sam/build-python3.11`） | △ | 王道。ただし Windows 環境への Docker Desktop 導入コストが Phase 1.5 の主目的（「最短で動かす」）と釣り合わない |
| AWS SAM CLI（`sam build --use-container`） | △ | AWS 公式の標準ルート。CI/CD 前提なら本命だが、Phase 1.5 単発の zip を作るためだけに学習コストを払う段階ではない |
| **AWS CloudShell** | ✅ | Amazon Linux + Python 3.11 が Lambda ランタイムと同一、AWS CLI 認証も済み、追加導入ゼロ |

**判断**: Phase 1.5 は「最短で動く環境を立ち上げる」ことを優先し、CloudShell を採用。ただし以下の **脱却条件** を明示しておく — CloudShell は手動操作の世界であり再現性・自動化の点で永続解にならないため、いずれかに当てはまった時点で Phase 3a（GitHub Actions OIDC）に移行する：

- デプロイ頻度が週 1 回を超える
- 複数人または別マシンから触る必要が出る
- リリース前に自動テストを通したくなる

**運用上の注意**:
- CloudShell は 20分無操作で切断、`/tmp` のデータは消える → 作業はその場で完結させる
- ローカルの Python バージョンと Lambda ランタイムが一致していること（Python 3.13 でビルドした zip は Lambda 3.11 で動かない）

**デプロイ時に直面した課題と切り分け**:

#### ① 仮想環境とランタイム環境のギャップによる 500 エラー

デプロイ直後、フロントから API を叩くと 500 が返った。ブラウザ DevTools の Console と CloudWatch Logs を突き合わせて切り分けた結果、原因が 2 つ複合していた：

- **`pyproject.toml` の依存定義漏れ**: ローカル venv に `pip install` で個別に入れていた `python-multipart`（FastAPI の `UploadFile` 受信に必須）が、`pyproject.toml` の `dependencies` に書き漏れていた。ローカルでは venv にインストール済みのため動作してしまい、デプロイ直前まで欠落に気付けなかった
- **バイナリ互換性のズレ**: ローカル（Windows）の `pip install` で取得した `pydantic-core` などのネイティブ拡張は、Lambda 実行環境（Amazon Linux）のバイナリと不整合で起動時に ImportError を起こす

対応として、`pyproject.toml` に欠けていた依存を追記したうえで、CloudShell（Amazon Linux + Python 3.11）に環境を揃え、`pip install --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.11` で Lambda ランタイム互換の wheel を明示的に取得し直して zip を再構築した。

**学び**: 「ローカルで動く」は本番互換性の保証にならない。依存は宣言ファイル（`pyproject.toml`）を一次情報源とし、ビルドは本番に近い環境で行うことを原則とする。

#### ② Lambda 同時実行数の二重防御を試みた際のアカウント上限制約

API Gateway スロットリングに加え、Lambda 側にも Reserved Concurrency = 20 を設定して二重防御を構築しようとしたところ、保存時に「アカウントの同時実行数: -10」というエラーで弾かれた。

調査の結果、新規 AWS アカウントは安全措置として **アカウント全体の同時実行数上限が 10 にロック** されており、Reserved Concurrency は「アカウント上限 - Unreserved 確保分（最低 10 必要）」を超えて設定できない仕様だった。つまり現アカウントでは、Lambda 側で個別に絞らずとも構造的に最大同時実行数 10 という強い上限が既に効いている。

対応として、Reserved Concurrency は設定せず、API Gateway スロットリング（rate 10 req/秒）とアカウント側のデフォルト上限（10）の組み合わせで十分と判断し、現行構成のまま運用に乗せた。アカウント上限の引き上げが認められたタイミングで Reserved Concurrency を再検討する。

**Lambda 主要設定値とその根拠**:

| 設定 | 値 | 根拠 |
|---|---|---|
| メモリ | **512 MB** | Lambda は割り当てメモリに比例して vCPU 性能が配分される設計。CEST のワークロードは組み合わせ列挙 → パレート抽出 → robustness 計算と **CPU バウンド** が中心で、I/O 待ちはほぼない。デフォルト 128MB から 512MB に引き上げることで実測の `evaluate_combo` 実行時間が体感で 3〜4 倍速くなる。1024MB 以上は現在の入力サイズでは頭打ちで費用対効果が悪く、Phase 4（Bedrock 呼び出し追加）のタイミングで再評価する |
| タイムアウト | **30 秒** | API Gateway HTTP API の統合タイムアウトが既定 30 秒（最大も 30 秒）。Lambda 側のタイムアウトを **API Gateway より長く設定しても、API Gateway 側が先に 504 を返してクライアント接続を切る** ため、ユーザーに返るエラー体験は変わらず、Lambda の実行課金時間だけが伸びる無駄が出る。両者を 30 秒に揃えることで、ユーザーが受け取るエラーと課金される実行時間を一致させる |
| 同時実行数 | **未設定** | 上記 ② のとおり、アカウント上限 10 と API Gateway スロットリングで構造的に上限が効いているため |
| ランタイム | **Python 3.11** | Mangum が ASGI 3 系を要求、かつ Lambda が安定サポートする最新版（Python 3.12/3.13 は依存ライブラリの wheel 提供が遅れることがある） |
| ハンドラ | `cest.main.handler` | `main.py` 内で `handler = Mangum(app)` を export |

---

### Phase 2: 独自ドメイン（Route 53 + ACM）— ⏳ 計画中

**目的**: 独自ドメインで HTTPS 配信、HSTS プリロードで通信を保護する

**方針**:
- Route 53 にホストゾーンを作成し、レジストラから DNS 委任
- ACM で SSL 証明書を発行（CloudFront 用は us-east-1 リージョンのみ対応している点に注意）
- CloudFront に代替ドメイン名と ACM 証明書を設定、Route 53 で Alias レコードを CloudFront に向ける

**懸念**: DNS 伝播と CloudFront 反映で数十分〜数時間かかる可能性。

---

### Phase 3a: GitHub Actions 自動 CI/CD — ✅ 完了（2026-08-11）

**目的**: 手動デプロイのヒューマンエラーを排除し、`git push` を唯一のリリーストリガーにする

**実施内容（要点）**:
- インフラ自体を Terraform でコード化（`infra/`）。S3・CloudFront・API Gateway は既存リソースを `terraform import` で取り込み、Lambda は Phase 3b と合わせて新規（コンテナ版）作成
- IAM OIDC プロバイダで GitHub Actions に短命クレデンシャルを発行（アクセスキーをGitHub Secretsにも直書きしない）。信頼ポリシーは対象リポジトリ・`main`ブランチに限定
- ワークフロー構成（`.github/workflows/deploy.yml`）: `pytest` → `docker build/push`(ECR) → `terraform apply`(Lambda更新) → `station_master.json`同期 → `API_GATEWAY_PLACEHOLDER`置換 → S3 sync → CloudFront Invalidation
- **CI用ロールにはIAM/OIDCプロバイダ自体を触る権限を渡していない**（CIが自分の信頼関係を自分で書き換えられる状態を避けるため）。そのため `terraform apply` は `-target=aws_lambda_function.cest_api` でLambda関数のみを対象にし、IAMロールやOIDC設定を変更する場合は人間が手元/CloudShellからフル `terraform apply` を実行する運用にした

**デプロイ時に直面した課題と切り分け**:

#### ① Terraform importと実物のズレ

既存リソースを `terraform import` した直後、`terraform plan` で「API GatewayのCORS設定が削除される」「CloudFrontのタグ・OACの名前/説明が変わる」という差分が出た。いずれも `.tf` を書く際に実物の設定を見落としていたのが原因。**`apply`前に必ず`plan`で差分ゼロを確認する**運用の効果がここで実際に出た（CORS設定を消していたら、ブラウザからのAPI呼び出しが壊れていた可能性がある）。

#### ② CI用IAMロールの権限を後から一つずつ発見

最小権限を意識してCI用ロールの権限を絞ったところ、初回のワークフロー実行で `ecr:CreateRepository` のAccessDeniedから始まり、`ecr:ListTagsForResource`・`iam:ListRolePolicies`・`iam:ListAttachedRolePolicies`・`s3:DeleteObject`（stateロック解放用）・`lambda:ListVersionsByFunction` と、**Terraformが「変更してない部分」を確認するためのstate refresh処理だけでも複数の読み取り権限が必要**なことが分かった。CloudFrontやLambdaの管理系AWSプロバイダは、実際に変更する権限（Update系）だけでなく、現況を読み取る権限（List/Describe/Get系）もセットで要求してくる。1つずつ実行→AccessDenied→権限追加→再実行、を繰り返して特定した。

**学び**: 最小権限を狙うときも、「実際に変更したい操作」だけでなく「Terraformが差分確認のために読みに行く操作」まで含めて設計しないと、初回実行で必ず引っかかる。

#### ③ 失敗したapplyがstateロックを残す

権限不足で`terraform apply`が失敗した際、S3ネイティブロック（`use_lockfile`）の解放にも同じ権限不足が影響し、ロックファイルが残った。次の実行が「state is locked」で失敗したため、`terraform force-unlock <LOCK_ID>` で手動解除してから再実行した。

---

### Phase 3b: zip → Container Image 移行 — ✅ 完了（Phase 3aと同時実施、2026-08-11）

**目的**: 依存パッケージサイズの制約（zip は 250MB 制限）を回避、ビルド環境の差異（Windows/Linuxバイナリ非互換）を構造的に解消

**実施内容（要点）**:
- `public.ecr.aws/lambda/python:3.11` ベースの `cest/Dockerfile` を作成。`pyproject.toml`と`src/`をコピーし`pip install .`
- ECR にイメージを push → Lambda の実行形式を Container Image に切り替え（`package_type = "Image"`）
- 旧zip版Lambda関数は削除してから、同じ関数名でコンテナ版を新規作成（LambdaのPackageTypeは作成後に変更不可のため、その場更新ではなく作り直しが必要。関数名を同じにすることでARNが変わらず、API Gateway側の統合設定は無変更で済んだ）
- イメージタグにはgitのコミットSHAを使用（`:latest`のようなタグ使い回しだと、Terraformが変更を検知できずLambdaが更新されない）

**デプロイ時に直面した課題と切り分け**:

#### ① `pip install .` でパッケージデータが欠落する

Dockerfileで`pip install .`（非editableインストール）を実行したところ、`cest/src/cest/data/*.json`（station_master.json等）がインストール先に含まれないことが判明。`pyproject.toml`に`package-data`の設定が無く、setuptoolsのデフォルト挙動では`.py`ファイル以外は同梱されない仕様だった。

これまで問題が顕在化しなかった理由: ローカル開発は編集可能インストール（`pip install -e .`、コードを実際にコピーせずソースの場所を直接参照するため、データファイルも自然に見つかる）、旧zipデプロイはpipを介さず手動でフォルダごとコピーしていたため、どちらも本物の「pipパッケージング」を通していなかった。今回コンテナ化で初めて`pip install .`を実行し、初めて顕在化した。

`pyproject.toml`に以下を追加して解決:
```toml
[tool.setuptools.package-data]
cest = ["data/*.json"]
```

**学び**: 「ローカルで動く」「今までのデプロイ方法で動いてた」は、パッケージングの正しさの証明にはならない。依存関係だけでなく、パッケージに何が含まれるかも宣言ファイル(`pyproject.toml`)を一次情報源にする。

---

### Phase 4: Bedrock 統合（v0.4 機能）— ⏳ 計画中

**目的**: 分析結果に対する自然言語Q&Aを実装。Lambda → Bedrock を IAM で認可することで、外部 API キー管理を不要にする

**方針**:
- Bedrock コンソールで Claude 3 Haiku のモデルアクセスを有効化
- Lambda の IAM Role に `bedrock:InvokeModel` 権限を追加
- `/ask` エンドポイントを実装、フロントにチャット UI を追加
- Lambda のメモリ 512MB → 1024MB、タイムアウト 30秒 → 60秒に拡張
- Bedrock エラー時はルールベース分析結果のみ表示するフォールバック

**コスト想定**: 月100クエリ程度なら月10円以下。

---

## 5. コスト爆発対策

### 実装済み

- **API Gateway スロットリング**：ステージのデフォルトルートで rate **10 req/秒**、burst **10** に設定
  - アカウントデフォルト（rate 10000 / burst 5000）の **1/1000** に絞ることで、DDoS的アクセスや想定外コストを物理的にブロック
  - 個人プロジェクトのデモ用途では rate 10 で十分実用範囲、超過したリクエストは 429 で拒否される
- **Lambda 側 Reserved Concurrency は未設定**：二重防御として設定を試みたが、新規 AWS アカウントは安全措置でアカウント全体の同時実行数上限が 10 にロックされており、構造的に既に強い上限が効いている。加えて API Gateway 側でも rate 10 req/秒 に絞っているため、Lambda 側で重ねて絞る必要なしと判断（詳細は Phase 1.5）

### 実装済み（追記）

- **WAF（CloudFront無料バンドル）**：CloudFront作成時にAWSが提案する基本保護（AWSManagedRulesAmazonIpReputationList等）が有効になっていた。当初「WAFは採用しない」という方針だったため追加課金を疑ったが、コンソール上で「CloudFront料金の無料プランに含まれる」設定であることを確認。追加コストが無く実用的な保護でもあるため、削除せずそのまま維持することにした（意図せず有効化されていたものを、実態調査の上で追認した形）

### 計画中

- **AWS Budgets**：月額閾値（$10）超過時に SNS で通知
- **CloudWatch Alarms**：Lambda 実行回数 / S3 ストレージ / CloudFront 転送量を個別監視
- **CloudWatch Logs の保持期間設定**：デフォルトは無期限なので、Lambda ログを 7〜30日に絞る

### 実装順の考え方

- ✅ API Gateway スロットリングが最初に来た理由：**設定一つで物理的にコスト上限が決まる**ため、観測より先に「上限の蓋」を閉めた
- ✅ CI/CD自動化（Phase 3a/3b）は完了。次に観測性（Budgets + CloudWatch Alarms）を導入し、想定外コストの早期検知ができる状態にする
- ⏳ スロットリング閾値の調整は、実アクセス傾向を Alarms で見てから決める

---

## 6. デプロイ対象ファイル

### フロントエンド（S3 にアップロード、GitHub Actionsが自動生成）
```
web/
├── index.html            ← API_GATEWAY_PLACEHOLDERはデプロイ時に実URLへ置換される
└── station_master.json   ← cest/src/cest/data/station_master.json からデプロイ時にコピー（Git管理外）
```

### バックエンド（Lambda コンテナイメージとしてECR経由でデプロイ）
```
cest/Dockerfile が public.ecr.aws/lambda/python:3.11 をベースにビルド
cest/src/cest/      ← パッケージ全体（pip install . で導入、data/*.jsonもpackage-data設定で同梱）

依存ライブラリ（pyproject.toml）:
- fastapi
- pydantic
- networkx
- jsonschema
- referencing
- mangum    ← Lambda アダプタ
（uvicorn は不要、boto3 は Lambda 標準搭載）
```

---

## 7. コスト試算（最終形）

| サービス | 12ヶ月以内 | 12ヶ月以降 |
|---|---|---|
| S3 + CloudFront | 無料 | 無料 |
| Lambda (Container Image) | 無料 | 無料 |
| API Gateway | 無料 | $0〜$1/月 |
| Bedrock (Haiku, 月100クエリ) | ~10円/月 | ~10円/月 |
| Route 53 ホストゾーン | $0.5/月 (約75円) | 同左 |
| ドメイン年額 | 約1500円 (月83円) | 同左 |
| ECR (Container Image格納) | 無料 | ~$0〜$0.5/月 |
| GitHub Actions | 無料 | 無料 |
| **合計** | **約170円/月** | **約180〜250円/月** |

---

## 8. セキュリティ要件

| 要件 | 対応 |
|---|---|
| 通信暗号化 | CloudFront HTTPS、S3 直接アクセス禁止（OAC） |
| 認証 | なし（公開デモ用途のため）。Phase 4 後に API Gateway のレート制限を追加検討 |
| CORS | 現状 `*`（独自ドメイン未確定のため）。Phase 2（独自ドメイン）完了後に `https://yuki-shimada.dev` へ絞る |
| Lambda 権限 | 最小権限。Phase 4 で `bedrock:InvokeModel` 追加 |
| AWS認証情報 | コード・GitHub Secretsへの直書き禁止。GitHub Actions は OIDC 経由の短命クレデンシャルのみ使用（Phase 3aで実装） |
| Bedrock 入力 | システムプロンプトで応答範囲を制限（プロンプトインジェクション対策） |

---

## 9. 将来拡張（スコープ外）

- 探索モード（最適エリア逆算、v0.4 内で検討中）
- WAFの本格運用（現状はCloudFront無料バンドルの基本保護のみ。有料のカスタムルール追加等は個人プロジェクトの規模では費用対効果が見合わないため当面なし）
- Cognito 認証（公開デモという用途と合わないため当面なし）
- 結果の永続化（DynamoDB）
- カスタムロギング（CloudWatch Logs Insights）

---

## 10. 環境・前提

### 開発環境
- ローカル: Windows 11 / PowerShell
- Python: ローカル 3.13 / Lambda ランタイム 3.11
- CI/CDのビルド環境: GitHub Actions（`ubuntu-latest`、Docker同梱）
- 手動運用・インフラ変更用: AWS CloudShell（Linux, Python 3.11, AWS CLI / Terraform 同梱）。IAM/OIDCプロバイダなどCIに権限を渡していないリソースの変更時のみ使用

### AWS 環境
- アカウント: 個人アカウント（無料枠期間内）
- リージョン: `ap-northeast-1`（CloudFront 用証明書のみ `us-east-1`）
- 認証情報: 人間の手動操作は IAM ユーザー（`cest-admin`）、GitHub Actions は OIDC 経由の短命クレデンシャル（`cest-github-actions-deploy`ロール）。長期アクセスキーはGitHub Secretsにも保存していない
- インフラのコード管理: Terraform（`infra/`）。stateは `cest-terraform-state-yuki-shimada` バケットにS3ネイティブロックで管理
