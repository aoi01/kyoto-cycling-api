# 京都自転車安全ルートナビ API

京都を自転車で安全に観光するためのルート案内APIです。

## 機能

- **安全ルート検索**: A*アルゴリズムによる安全道を考慮したルート計算
- **駐輪場経由ルート (UC-1)**: 目的地付近の駐輪場を経由するルート
- **直接ルート (UC-2)**: 出発地から目的地への直接ルート
- **シェアサイクル対応 (UC-3)**: GBFS連携（docomo, hellocycling）
- **音声ナビ指示**: Mapbox Map Matching APIによる音声案内

## 技術スタック

- **FastAPI** + **Pydantic v2**
- **NetworkX** + **OSMnx** - ルート探索
- **GBFS** - シェアサイクル連携
- **Mapbox API** - 音声ナビ指示

## セットアップ

### 1. 依存関係のインストール

```bash
# uvを使用する場合
uv sync

# pipを使用する場合
pip install -e .
```

### 2. 環境変数の設定

```bash
# .envファイルを作成
MAPBOX_ACCESS_TOKEN=your_mapbox_token
```

### 3. サーバー起動

```bash
# uvを使用する場合
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 直接実行する場合
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API エンドポイント

### GET /api/route

ルート検索

**パラメータ:**
| パラメータ | 型 | 必須 | 説明 |
|-----------|-----|-----|------|
| `origin` | string | ✓ | 出発地 "経度,緯度" |
| `destination` | string | ✓ | 目的地 "経度,緯度" |
| `mode` | string | ✓ | "my-cycle" / "share-cycle" |
| `safety` | int | ✓ | 1-10 |
| `needParking` | bool | - | 駐輪場案内が必要か |
| `operators` | string | - | 事業者（カンマ区切り） |

### GET /api/ports

シェアサイクルポート一覧

**パラメータ:**
| パラメータ | 型 | 必須 | 説明 |
|-----------|-----|-----|------|
| `operators` | string | ✓ | 事業者（カンマ区切り） |
| `near` | string | - | 中心座標 "経度,緯度" |
| `radius` | int | - | 半径（メートル） |
| `minBikes` | int | - | 最低空き台数 |
| `minDocks` | int | - | 最低空きドック数 |

### GET /health

ヘルスチェック

## 安全度パラメータ

| safety | 説明 |
|--------|------|
| 1 | 最短距離重視 |
| 3 | バランス |
| 5 | 安全最優先（安全道を大幅に優遇） |

## データ

- **道路グラフ**: `app/data/graph/kyoto_bike_graph.pkl` (NetworkX MultiDiGraph)
- **駐輪場データ**: `app/data/parkings.py` (252件、京都市オープンデータより)

## ドキュメント

詳細は [API reference.md](API%20reference.md) を参照してください。

## ライセンス

MIT License
