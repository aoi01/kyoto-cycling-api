# 京都自転車安全ルートナビ API 使用ガイド

Google Cloud（Cloud Run）にデプロイ後のAPI使用方法をまとめたガイドです。

## ベースURL

```
https://your-service-name.run.app
```

※実際のURLはCloud Runデプロイ時に発行されます。

---

## エンドポイント一覧

| エンドポイント | メソッド | 説明 |
|---------------|---------|------|
| `/health` | GET | ヘルスチェック |
| `/api/route` | GET | ルート検索 |
| `/api/ports` | GET | シェアサイクルポート一覧 |

---

## 1. ヘルスチェック

### リクエスト

```
GET /health
```

### レスポンス

```json
{
  "status": "healthy"
}
```

### 使用例

```bash
curl https://your-service-name.run.app/health
```

---

## 2. ルート検索 API

### リクエスト

```
GET /api/route
```

### パラメータ

| パラメータ | 型 | 必須 | 説明 | 例 |
|-----------|-----|-----|------|-----|
| `origin` | string | ✓ | 出発地 "経度,緯度" | `135.7588,34.9858` |
| `destination` | string | ✓ | 目的地 "経度,緯度" | `135.7482,35.0142` |
| `mode` | string | ✓ | 移動モード | `my-cycle` / `share-cycle` |
| `safety` | int | ✓ | 安全度 1-10 | `5` |
| `needParking` | bool | - | 駐輪場案内が必要か | `true` / `false` |
| `operators` | string | - | シェアサイクル事業者（カンマ区切り） | `docomo,hellocycling` |

### 安全度パラメータの意味

| safety | 説明 |
|--------|------|
| 1 | 最短距離重視（危険な道も通る） |
| 5 | バランス |
| 10 | 安全最優先（安全道を大幅に優遇） |

---

### ユースケース別使用例

#### UC-1: 自転車で行って駐輪場に停めて歩く

```bash
curl "https://your-service-name.run.app/api/route?\
origin=135.7588,34.9858&\
destination=135.7482,35.0142&\
mode=my-cycle&\
safety=5&\
needParking=true"
```

#### UC-2: 自転車で直接目的地へ

```bash
curl "https://your-service-name.run.app/api/route?\
origin=135.7588,34.9858&\
destination=135.7482,35.0142&\
mode=my-cycle&\
safety=5&\
needParking=false"
```

#### UC-3: シェアサイクルを使う

```bash
curl "https://your-service-name.run.app/api/route?\
origin=135.7588,34.9858&\
destination=135.7482,35.0142&\
mode=share-cycle&\
safety=5&\
operators=docomo"
```

---

### レスポンス例

#### 成功時（UC-2: 直接ルート）

```json
{
  "success": true,
  "data": {
    "segments": [
      {
        "type": "bicycle",
        "mode": "my-cycle",
        "startPoint": {
          "type": "origin",
          "name": "出発地",
          "coordinates": [135.7588, 34.9858]
        },
        "endPoint": {
          "type": "destination",
          "name": "目的地",
          "coordinates": [135.7482, 35.0142]
        },
        "geometry": {
          "type": "LineString",
          "coordinates": [
            [135.7588, 34.9858],
            [135.7550, 35.0000],
            [135.7482, 35.0142]
          ]
        },
        "distance": 3200,
        "duration": 768,
        "voiceInstructions": [
          {
            "text": "100m先を右折",
            "distanceFromStart": 500,
            "maneuverType": "turn-right"
          }
        ]
      }
    ],
    "summary": {
      "totalDistance": 3200,
      "totalDuration": 768,
      "safetyScore": 7.5
    }
  },
  "error": null
}
```

#### 成功時（UC-1: 駐輪場経由）

```json
{
  "success": true,
  "data": {
    "segments": [
      {
        "type": "bicycle",
        "mode": "my-cycle",
        "startPoint": {
          "type": "origin",
          "name": "出発地",
          "coordinates": [135.7588, 34.9858]
        },
        "endPoint": {
          "type": "parking",
          "name": "二条城前駐輪場",
          "coordinates": [135.7485, 35.0140]
        },
        "geometry": {
          "type": "LineString",
          "coordinates": [...]
        },
        "distance": 3100,
        "duration": 744
      },
      {
        "type": "walk",
        "mode": "walk",
        "startPoint": {
          "type": "parking",
          "name": "二条城前駐輪場",
          "coordinates": [135.7485, 35.0140]
        },
        "endPoint": {
          "type": "destination",
          "name": "目的地",
          "coordinates": [135.7482, 35.0142]
        },
        "distance": 50,
        "duration": 36
      }
    ],
    "parking": {
      "id": "parking_123",
      "name": "二条城前駐輪場",
      "coordinates": [135.7485, 35.0140],
      "feeDescription": "2時間まで無料"
    },
    "summary": {
      "totalDistance": 3150,
      "totalDuration": 780,
      "safetyScore": 8.2
    }
  }
}
```

#### 成功時（UC-3: シェアサイクル）

```json
{
  "success": true,
  "data": {
    "segments": [
      {
        "type": "walk",
        "mode": "walk",
        "startPoint": {
          "type": "origin",
          "coordinates": [135.7588, 34.9858]
        },
        "endPoint": {
          "type": "borrow_port",
          "name": "京都駅八条口ポート",
          "coordinates": [135.7590, 34.9855]
        },
        "distance": 30,
        "duration": 21
      },
      {
        "type": "bicycle",
        "mode": "share-cycle",
        "operator": "docomo",
        "startPoint": {
          "type": "borrow_port",
          "name": "京都駅八条口ポート",
          "coordinates": [135.7590, 34.9855]
        },
        "endPoint": {
          "type": "return_port",
          "name": "二条城ポート",
          "coordinates": [135.7480, 35.0145]
        },
        "geometry": {
          "type": "LineString",
          "coordinates": [...]
        },
        "distance": 3100,
        "duration": 744
      },
      {
        "type": "walk",
        "mode": "walk",
        "startPoint": {
          "type": "return_port",
          "coordinates": [135.7480, 35.0145]
        },
        "endPoint": {
          "type": "destination",
          "coordinates": [135.7482, 35.0142]
        },
        "distance": 40,
        "duration": 29
      }
    ],
    "borrowPort": {
      "id": "docomo_001",
      "name": "京都駅八条口ポート",
      "operator": "docomo",
      "coordinates": [135.7590, 34.9855],
      "bikesAvailable": 5,
      "docksAvailable": 10
    },
    "returnPort": {
      "id": "docomo_025",
      "name": "二条城ポート",
      "operator": "docomo",
      "coordinates": [135.7480, 35.0145],
      "bikesAvailable": 2,
      "docksAvailable": 8
    },
    "summary": {
      "totalDistance": 3170,
      "totalDuration": 794,
      "safetyScore": 7.8
    }
  }
}
```

#### エラー時

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "INVALID_ORIGIN",
    "message": "出発地の座標が不正です"
  }
}
```

### エラーコード一覧

| コード | 説明 |
|--------|------|
| `INVALID_ORIGIN` | 出発地の座標が不正または京都市外 |
| `INVALID_DESTINATION` | 目的地の座標が不正または京都市外 |
| `NO_ROUTE_FOUND` | ルートが見つからない |
| `NO_PARKING_FOUND` | 目的地付近に駐輪場がない |
| `NO_PORTS_AVAILABLE` | 利用可能なシェアサイクルポートがない |
| `GBFS_API_ERROR` | シェアサイクルAPIエラー |

---

## 3. シェアサイクルポート一覧 API

### リクエスト

```
GET /api/ports
```

### パラメータ

| パラメータ | 型 | 必須 | 説明 | 例 |
|-----------|-----|-----|------|-----|
| `operators` | string | ✓ | 事業者（カンマ区切り） | `docomo,hellocycling` |
| `near` | string | - | 中心座標 "経度,緯度" | `135.7588,34.9858` |
| `radius` | int | - | 半径（メートル）100-5000 | `500` |
| `minBikes` | int | - | 最低空き台数 | `1` |
| `minDocks` | int | - | 最低空きドック数 | `1` |

### 使用例

```bash
# 京都駅周辺500m以内のdocomoポート（空き3台以上）
curl "https://your-service-name.run.app/api/ports?\
operators=docomo&\
near=135.7588,34.9858&\
radius=500&\
minBikes=3"
```

### レスポンス例

```json
{
  "success": true,
  "data": {
    "ports": [
      {
        "id": "docomo_001",
        "name": "京都駅八条口ポート",
        "operator": "docomo",
        "coordinates": [135.7590, 34.9855],
        "bikesAvailable": 5,
        "docksAvailable": 10,
        "isRenting": true,
        "isReturning": true,
        "lastReported": "2024-01-15T10:30:00Z"
      },
      {
        "id": "docomo_002",
        "name": "京都タワー前ポート",
        "operator": "docomo",
        "coordinates": [135.7585, 34.9870],
        "bikesAvailable": 3,
        "docksAvailable": 7,
        "isRenting": true,
        "isReturning": true,
        "lastReported": "2024-01-15T10:28:00Z"
      }
    ],
    "totalCount": 2,
    "lastUpdated": "2024-01-15T10:30:00Z"
  }
}
```

---

## フロントエンド実装例

### JavaScript (fetch)

```javascript
// ルート検索
async function searchRoute(origin, destination, mode, safety) {
  const params = new URLSearchParams({
    origin: `${origin.lng},${origin.lat}`,
    destination: `${destination.lng},${destination.lat}`,
    mode: mode,
    safety: safety.toString(),
    needParking: (mode === 'my-cycle').toString()
  });

  const response = await fetch(
    `https://your-service-name.run.app/api/route?${params}`
  );
  const data = await response.json();

  if (data.success) {
    return data.data;
  } else {
    throw new Error(data.error.message);
  }
}

// 使用例
const route = await searchRoute(
  { lng: 135.7588, lat: 34.9858 },  // 京都駅
  { lng: 135.7482, lat: 35.0142 },  // 二条城
  'my-cycle',
  5
);

// ルートをMapboxで表示
map.addSource('route', {
  type: 'geojson',
  data: {
    type: 'Feature',
    geometry: route.segments[0].geometry
  }
});
```

### Python (httpx)

```python
import httpx

async def search_route(origin, destination, mode, safety):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://your-service-name.run.app/api/route",
            params={
                "origin": f"{origin[0]},{origin[1]}",
                "destination": f"{destination[0]},{destination[1]}",
                "mode": mode,
                "safety": safety,
                "needParking": "false"
            }
        )
        data = response.json()

        if data["success"]:
            return data["data"]
        else:
            raise Exception(data["error"]["message"])

# 使用例
route = await search_route(
    (135.7588, 34.9858),  # 京都駅
    (135.7482, 35.0142),  # 二条城
    "my-cycle",
    5
)
print(f"距離: {route['summary']['totalDistance']}m")
print(f"所要時間: {route['summary']['totalDuration']}秒")
```

---

## 座標について

- 座標は **[経度, 緯度]** の順序（GeoJSON準拠）
- 京都市のバウンディングボックス:
  - 緯度: 34.85 ～ 35.15
  - 経度: 135.60 ～ 135.90
- 範囲外の座標はエラーになります

### 主要スポットの座標

| 場所 | 経度 | 緯度 |
|------|------|------|
| 京都駅 | 135.7588 | 34.9858 |
| 二条城 | 135.7482 | 35.0142 |
| 金閣寺 | 135.7292 | 35.0394 |
| 清水寺 | 135.7850 | 34.9949 |
| 四条烏丸 | 135.7593 | 35.0038 |

---

## レート制限

Cloud Runのデフォルト設定では特にレート制限はありませんが、本番運用時は以下を推奨：

- 1クライアントあたり: 60リクエスト/分
- 全体: 1000リクエスト/分

---

## OpenAPI ドキュメント

デプロイ後、以下のURLでSwagger UIにアクセス可能：

```
https://your-service-name.run.app/docs
```

ReDocは以下：

```
https://your-service-name.run.app/redoc
```
