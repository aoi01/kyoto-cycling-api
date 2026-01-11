# Python 3.11ベースイメージ
FROM python:3.11-slim

# 作業ディレクトリを設定
WORKDIR /app

# システム依存関係のインストール
# NetworkXやNumPyのビルドに必要
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Python依存関係のインストール
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# アプリケーションコードとデータをコピー
COPY app ./app

# ポート設定（Cloud Runは環境変数PORTを使用）
ENV PORT=8080
EXPOSE 8080

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=2)"

# Uvicornでアプリケーションを起動
# --workers 1: Cloud Runは水平スケーリングするので1ワーカーで十分
# --timeout-keep-alive 75: Cloud Runのタイムアウトより少し短く
CMD exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port $PORT \
    --workers 1 \
    --timeout-keep-alive 75
