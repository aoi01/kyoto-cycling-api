#!/bin/bash

# Cloud Runデプロイスクリプト
# 使用方法: ./deploy.sh [PROJECT_ID] [MAPBOX_TOKEN]

set -e

# パラメータチェック
if [ $# -lt 2 ]; then
    echo "使用方法: ./deploy.sh [PROJECT_ID] [MAPBOX_TOKEN]"
    exit 1
fi

PROJECT_ID=$1
MAPBOX_TOKEN=$2
SERVICE_NAME="kyoto-cycling-api"
REGION="asia-northeast1"
REPOSITORY="kyoto-cycling-api"

echo "==================================="
echo "Cloud Run デプロイ開始"
echo "==================================="
echo "プロジェクト: $PROJECT_ID"
echo "サービス名: $SERVICE_NAME"
echo "リージョン: $REGION"
echo ""

# 1. プロジェクト設定
echo "1. プロジェクトを設定中..."
gcloud config set project $PROJECT_ID

# 2. 必要なAPIを有効化
echo "2. 必要なAPIを有効化中..."
gcloud services enable \
    artifactregistry.googleapis.com \
    run.googleapis.com \
    cloudbuild.googleapis.com

# 3. Artifact Registryリポジトリを作成（存在しない場合）
echo "3. Artifact Registryリポジトリを確認中..."
if ! gcloud artifacts repositories describe $REPOSITORY \
    --location=$REGION &> /dev/null; then
    echo "   リポジトリを作成中..."
    gcloud artifacts repositories create $REPOSITORY \
        --repository-format=docker \
        --location=$REGION \
        --description="Kyoto Cycling API Docker Repository"
else
    echo "   リポジトリは既に存在します"
fi

# 4. Dockerイメージをビルド＆プッシュ
echo "4. Dockerイメージをビルド＆プッシュ中..."
IMAGE_NAME="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/api:latest"

gcloud builds submit \
    --tag $IMAGE_NAME \
    --timeout=10m

# 5. Cloud Runにデプロイ
echo "5. Cloud Runにデプロイ中..."
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 300 \
    --max-instances 10 \
    --min-instances 0 \
    --set-env-vars MAPBOX_ACCESS_TOKEN=$MAPBOX_TOKEN

# 6. サービスURLを取得
echo ""
echo "==================================="
echo "デプロイ完了！"
echo "==================================="
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --format='value(status.url)')
echo "サービスURL: $SERVICE_URL"
echo ""
echo "ヘルスチェック: curl $SERVICE_URL/health"
echo "APIドキュメント: $SERVICE_URL/docs"
echo ""
