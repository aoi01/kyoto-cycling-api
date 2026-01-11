# Google Cloud Run デプロイガイド

このドキュメントでは、京都自転車安全ルートナビAPIをGoogle Cloud Runにデプロイする手順を説明します。

## 前提条件

1. **Google Cloudアカウント**
   - https://cloud.google.com/ でアカウント作成
   - 新規アカウントには$300の無料クレジット

2. **gcloud CLIのインストール**
   - https://cloud.google.com/sdk/docs/install
   - インストール後、`gcloud init` で初期化

3. **Mapbox アクセストークン**
   - https://account.mapbox.com/ でトークン取得

## デプロイ手順

### 方法1: 自動デプロイスクリプト（推奨）

```bash
# スクリプトに実行権限を付与
chmod +x deploy.sh

# デプロイ実行
./deploy.sh YOUR_PROJECT_ID YOUR_MAPBOX_TOKEN
```

### 方法2: 手動デプロイ

#### Step 1: Google Cloudプロジェクトの設定

```bash
# プロジェクトIDを設定
export PROJECT_ID="your-project-id"
gcloud config set project $PROJECT_ID

# 必要なAPIを有効化
gcloud services enable artifactregistry.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

#### Step 2: Artifact Registryリポジトリの作成

```bash
gcloud artifacts repositories create kyoto-cycling-api \
    --repository-format=docker \
    --location=asia-northeast1 \
    --description="Kyoto Cycling API"
```

#### Step 3: Dockerイメージのビルド＆プッシュ

```bash
# イメージをビルド＆プッシュ
gcloud builds submit \
    --tag asia-northeast1-docker.pkg.dev/$PROJECT_ID/kyoto-cycling-api/api:latest
```

#### Step 4: Cloud Runへのデプロイ

```bash
# Mapboxトークンを設定
export MAPBOX_TOKEN="your_mapbox_token"

# デプロイ
gcloud run deploy kyoto-cycling-api \
    --image asia-northeast1-docker.pkg.dev/$PROJECT_ID/kyoto-cycling-api/api:latest \
    --platform managed \
    --region asia-northeast1 \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 300 \
    --max-instances 10 \
    --set-env-vars MAPBOX_ACCESS_TOKEN=$MAPBOX_TOKEN
```

#### Step 5: デプロイ確認

```bash
# サービスURLを取得
SERVICE_URL=$(gcloud run services describe kyoto-cycling-api \
    --region=asia-northeast1 \
    --format='value(status.url)')

# ヘルスチェック
curl $SERVICE_URL/health

# APIドキュメントにアクセス
open $SERVICE_URL/docs
```

## 環境変数の管理（Secret Manager使用）

本番環境では、Secret Managerの使用を推奨します。

```bash
# Secretを作成
echo -n "your_mapbox_token" | \
    gcloud secrets create mapbox-token --data-file=-

# Cloud Runに権限を付与
gcloud secrets add-iam-policy-binding mapbox-token \
    --member="serviceAccount:$(gcloud projects describe $PROJECT_ID \
        --format='value(projectNumber)')-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

# Secretを使ってデプロイ
gcloud run deploy kyoto-cycling-api \
    --image asia-northeast1-docker.pkg.dev/$PROJECT_ID/kyoto-cycling-api/api:latest \
    --platform managed \
    --region asia-northeast1 \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 300 \
    --set-secrets MAPBOX_ACCESS_TOKEN=mapbox-token:latest
```

## CI/CD設定（GitHub Actions）

`.github/workflows/deploy.yml` を参照してください。

## コスト見積もり

**Cloud Run 無料枠:**
- 月200万リクエスト
- 180,000 vCPU秒
- 360,000 GiB秒

**推定コスト（無料枠超過後）:**
- 小規模（〜10万リクエスト/月）: $5-10
- 中規模（〜100万リクエスト/月）: $20-40
- 大規模（〜1000万リクエスト/月）: $100-200

## パフォーマンス最適化

### 1. メモリとCPUの調整

```bash
# より多くのメモリが必要な場合
gcloud run deploy kyoto-cycling-api \
    --memory 4Gi \
    --cpu 4
```

### 2. 最小インスタンス数の設定

コールドスタートを避けるため：

```bash
gcloud run deploy kyoto-cycling-api \
    --min-instances 1  # 常に1インスタンス起動
```

### 3. タイムアウトの調整

```bash
gcloud run deploy kyoto-cycling-api \
    --timeout 600  # 10分（最大）
```

## トラブルシューティング

### ログの確認

```bash
# リアルタイムログ
gcloud run services logs tail kyoto-cycling-api --region=asia-northeast1

# 最近のエラー
gcloud run services logs read kyoto-cycling-api \
    --region=asia-northeast1 \
    --limit=50 \
    --format="table(timestamp, severity, textPayload)"
```

### デプロイの削除

```bash
# サービスを削除
gcloud run services delete kyoto-cycling-api --region=asia-northeast1

# Artifact Registryのイメージを削除
gcloud artifacts docker images delete \
    asia-northeast1-docker.pkg.dev/$PROJECT_ID/kyoto-cycling-api/api:latest
```

## 参考リンク

- [Cloud Run ドキュメント](https://cloud.google.com/run/docs)
- [Cloud Build ドキュメント](https://cloud.google.com/build/docs)
- [Secret Manager ドキュメント](https://cloud.google.com/secret-manager/docs)
