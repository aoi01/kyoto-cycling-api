# 京都自転車安全ルートナビ API - リファレンスドキュメント

## 目次
1. [プロジェクト構成](#1-プロジェクト構成)
2. [データ層](#2-データ層appdata)
3. [モデル層](#3-モデル層appmodels)
4. [サービス層](#4-サービス層appservices)
5. [ルーター層](#5-ルーター層approuters)
6. [メインアプリケーション](#6-メインアプリケーション)
7. [公式ドキュメント参照一覧](#7-公式ドキュメント参照一覧)

---

## 1. プロジェクト構成

```
app/
├── __init__.py              # パッケージ初期化
├── main.py                  # FastAPIアプリケーション
├── data/                    # 静的データ
│   ├── __init__.py
│   ├── parkings.py          # 駐輪場データ（252件）
│   └── graph/               # 道路グラフデータ
│       └── kyoto_bike_graph.pkl  # NetworkXグラフ（pickle形式）
├── models/                  # Pydanticモデル
│   ├── __init__.py
│   ├── common.py            # 共通モデル（ApiResponse等）
│   ├── route.py             # ルート関連モデル
│   ├── port.py              # シェアサイクルポートモデル
│   └── parking.py           # 駐輪場モデル
├── services/                # ビジネスロジック
│   ├── __init__.py
│   ├── route_calculator.py  # ルート計算サービス
│   ├── gbfs_client.py       # GBFS APIクライアント
│   └── mapbox_client.py     # Mapbox APIクライアント
└── routers/                 # APIエンドポイント
    ├── __init__.py
    ├── route.py             # /api/route
    └── ports.py             # /api/ports
```

※ 観光スポット情報はフロントエンドで管理

---

## 2. データ層（app/data）

### 2.1 parkings.py - 駐輪場データ

京都市オープンデータより取得した駐輪場情報（252件）

| 要素 | 種別 | 役割 |
|------|------|------|
| `PARKINGS` | list[Parking] | 全駐輪場データリスト |
| `get_all_parkings()` | Function | 全駐輪場データを取得 |
| `get_parking_by_id()` | Function | IDで駐輪場を検索 |

```python
# 使用例
from app.data import PARKINGS, get_all_parkings, get_parking_by_id

all_parkings = get_all_parkings()  # 252件
parking = get_parking_by_id("parking_001")
```

#### Parkingデータ構造

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `id` | str | 駐輪場ID（例: "parking_001"） |
| `name` | str | 駐輪場名称 |
| `coordinates` | list[float] | 座標 [経度, 緯度] |
| `fee_description` | str | 料金説明 |

### 2.2 graph/ - 道路グラフデータ

OSMnxで取得・加工した京都市の道路ネットワークグラフ

| ファイル | 形式 | 説明 |
|---------|------|------|
| `kyoto_bike_graph.pkl` | pickle | NetworkX MultiDiGraph |

#### グラフ構造

**ノード属性:**

| 属性 | 型 | 説明 |
|------|-----|------|
| `x` | float | 経度 |
| `y` | float | 緯度 |
| `osmid` | int | OpenStreetMap ノードID |

**エッジ属性:**

| 属性 | 型 | 説明 |
|------|-----|------|
| `length` | float | 距離（メートル） |
| `is_safe` | bool | 安全道フラグ |
| `highway` | str | 道路種別（OSMタグ） |
| `name` | str | 道路名（存在する場合） |

```python
# グラフロード例
import pickle

with open("app/data/graph/kyoto_bike_graph.pkl", "rb") as f:
    graph = pickle.load(f)

print(f"Nodes: {len(graph.nodes):,}")  # 約67,700
print(f"Edges: {len(graph.edges):,}")  # 約175,000
```

#### is_safe判定基準

| 条件 | is_safe |
|------|---------|
| cycleway（自転車道） | True |
| path（小道・遊歩道） | True |
| residential（住宅街道路） | True |
| living_street（生活道路） | True |
| その他（primary, secondary等） | False |

---

## 3. モデル層（app/models）

### 3.1 common.py - 共通モデル

| クラス/関数 | 種別 | 役割 |
|------------|------|------|
| `T` | TypeVar | ジェネリック型パラメータ |
| `ErrorDetail` | Model | エラー詳細（code, message） |
| `ApiResponse[T]` | Model | 統一APIレスポンス |
| `GeoJSONPoint` | Model | GeoJSON Point型 |
| `GeoJSONLineString` | Model | GeoJSON LineString型 |
| `create_success_response()` | Function | 成功レスポンス作成 |
| `create_error_response()` | Function | エラーレスポンス作成 |

### 3.2 route.py - ルート関連モデル

| クラス/Enum | 種別 | 役割 |
|------------|------|------|
| `TransportMode` | Enum | 移動モード（my-cycle / share-cycle） |
| `SegmentType` | Enum | セグメント種別（walk / bicycle） |
| `PointType` | Enum | 地点種別（origin / destination / parking / port） |
| `RoutePoint` | Model | ルート上の地点 |
| `VoiceInstruction` | Model | 音声ナビ指示 |
| `RouteGeometry` | Model | ルートジオメトリ |
| `RouteSegment` | Model | ルートセグメント |
| `RouteSummary` | Model | ルートサマリー |
| `RouteData` | Model | ルート検索レスポンス |

### 3.3 port.py - シェアサイクルポートモデル

| クラス | 種別 | 役割 |
|-------|------|------|
| `Port` | Model | シェアサイクルポート |
| `PortsData` | Model | ポート一覧レスポンス |
| `GBFSStationInfo` | Model | GBFS station_information（内部用） |
| `GBFSStationStatus` | Model | GBFS station_status（内部用） |

### 3.4 parking.py - 駐輪場モデル

| クラス | 種別 | 役割 |
|-------|------|------|
| `Parking` | Model | 駐輪場情報 |
| `ParkingsData` | Model | 駐輪場一覧レスポンス |

---

## 4. サービス層（app/services）

### 4.1 route_calculator.py

| クラス/関数 | 種別 | 役割 |
|------------|------|------|
| `RouteResult` | Dataclass | ルート計算結果（内部用） |
| `WeightCalculator` | Class | エッジ重み計算 |
| `haversine_distance()` | Function | Haversine距離計算 |
| `create_heuristic()` | Function | A*ヒューリスティック生成 |
| `calculate_bounding_box()` | Function | バウンディングボックス計算 |
| `create_subgraph_view()` | Function | サブグラフビュー作成 |
| `RouteCalculator` | Class | ルート計算サービス |

#### RouteCalculator メソッド一覧

| メソッド | 役割 |
|---------|------|
| `__init__(graph, parkings)` | 初期化（グラフと駐輪場データを受け取る） |
| `_precompute_edge_costs()` | 重み事前計算（起動時に実行） |
| `_get_weight(safety)` | 重み取得 |
| `_find_nearest_node(lon, lat)` | 最寄りノード検索 |
| `_find_path_astar(graph, orig, dest, weight)` | A*探索 |
| `_find_route_with_subgraph(origin, dest, safety)` | サブグラフ使用探索 |
| `_calculate_route_info(route)` | ルート情報計算 |
| `calculate_direct_route(origin, dest, safety)` | 直接ルート（UC-2） |
| `calculate_route_with_parking(origin, dest, safety)` | 駐輪場経由（UC-1） |
| `calculate_share_cycle_route(origin, dest, safety, ports)` | シェアサイクル（UC-3） |

### 4.2 gbfs_client.py

| クラス/定数 | 種別 | 役割 |
|------------|------|------|
| `KYOTO_BBOX` | Const | 京都市バウンディングボックス |
| `GBFS_ENDPOINTS` | Const | 事業者別エンドポイント |
| `CacheEntry` | Class | キャッシュエントリ |
| `GBFSClient` | Class | GBFSクライアント |

#### GBFSClient メソッド一覧

| メソッド | 役割 |
|---------|------|
| `initialize()` | 起動時初期化 |
| `close()` | クライアントクローズ |
| `get_ports(operators, near, radius, min_bikes, min_docks)` | ポート取得 |

### 4.3 mapbox_client.py

| クラス | 種別 | 役割 |
|-------|------|------|
| `MapboxClient` | Class | Mapbox APIクライアント |

#### MapboxClient メソッド一覧

| メソッド | 役割 |
|---------|------|
| `close()` | クライアントクローズ |
| `map_match(coordinates, profile)` | Map Matching API（座標を道路にスナップ＋音声指示取得） |
| `get_directions(origin, destination, waypoints, profile)` | Directions API（始点・終点から音声指示取得） |
| `validate_token()` | トークン検証 |

#### map_match の waypoints パラメータ

Map Matching APIでは、座標リストの中で「実際の経由地点」のインデックスを指定できる。
始点(0)と終点(最後のインデックス)のみを指定することで、中間座標はルート形状の参考としてのみ使用され、
「○つ目の目的地に到着しました」という不要な音声指示が出ない。

```python
# waypoints="0;{len(coordinates)-1}" で始点・終点のみを経由地として指定
```

---

## 5. ルーター層（app/routers）

### 5.1 route.py - GET /api/route

| パラメータ | 型 | 必須 | 説明 |
|-----------|-----|-----|------|
| `origin` | string | ✓ | 出発地 "経度,緯度" |
| `destination` | string | ✓ | 目的地 "経度,緯度" |
| `mode` | string | ✓ | "my-cycle" / "share-cycle" |
| `safety` | int | ✓ | 1-10 |
| `needParking` | bool | - | 駐輪場案内が必要か（デフォルト: true） |
| `operators` | string | - | 事業者（カンマ区切り、share-cycle時に使用） |

#### route.py 内部ヘルパー関数

| 関数 | 役割 |
|------|------|
| `_calculate_bearing(lon1, lat1, lon2, lat2)` | 2点間の方位角を計算（0-360度） |
| `_angle_difference(bearing1, bearing2)` | 2つの方位角の差を計算（0-180度） |
| `_extract_turn_points(coordinates, angle_threshold, max_waypoints)` | 曲がり角を抽出（未使用） |
| `_filter_voice_instructions(instructions, min_distance_between)` | 音声指示をフィルタリング |
| `_simplify_coordinates(coordinates, tolerance, max_count)` | Douglas-Peuckerで座標を簡略化 |
| `_get_voice_instructions(origin, destination, coordinates, mapbox_client)` | Mapbox APIで音声指示を取得 |

#### Douglas-Peucker座標簡略化

ルート座標が多すぎる場合（Map Matching APIの上限100点）、Douglas-Peuckerアルゴリズムで簡略化する。

```python
# tolerance=0.0001 は約11m、形状を保ちながら座標数を削減
# 例: 148点 → 28点（81%削減）
```

### 5.2 ports.py - GET /api/ports

| パラメータ | 型 | 必須 | 説明 |
|-----------|-----|-----|------|
| `operators` | string | ✓ | 事業者（カンマ区切り） |
| `near` | string | - | 中心座標 "経度,緯度" |
| `radius` | int | - | 半径（メートル） |
| `minBikes` | int | - | 最低空き台数 |
| `minDocks` | int | - | 最低空きドック数 |

---

## 6. メインアプリケーション（app/main.py）

### 起動時のデータロード

```python
# Lifespan内での処理
async def lifespan(app: FastAPI):
    # 1. 道路グラフロード
    graph = load_graph("app/data/graph/kyoto_bike_graph.pkl")

    # 2. 駐輪場データロード
    from app.data import PARKINGS
    parkings = PARKINGS

    # 3. RouteCalculator初期化（グラフ＋駐輪場）
    route_calculator = RouteCalculator(graph, parkings=parkings)

    # 4. GBFSClient初期化
    gbfs_client = GBFSClient()
    await gbfs_client.initialize()

    # 5. MapboxClient初期化
    mapbox_client = MapboxClient(settings.MAPBOX_ACCESS_TOKEN)

    # 6. app.stateに格納
    app.state.graph = graph
    app.state.parkings = parkings
    app.state.route_calculator = route_calculator
    app.state.gbfs_client = gbfs_client
    app.state.mapbox_client = mapbox_client
    ...
```

### app.state に格納されるオブジェクト

| キー | 型 | データソース | 説明 |
|-----|-----|-------------|------|
| `graph` | nx.MultiDiGraph | `app/data/graph/*.pkl` | 道路グラフ |
| `parkings` | list[Parking] | `app/data/parkings.py` | 駐輪場リスト（252件） |
| `route_calculator` | RouteCalculator | - | ルート計算サービス |
| `gbfs_client` | GBFSClient | 外部API（GBFS） | GBFSクライアント |
| `mapbox_client` | MapboxClient | 外部API（Mapbox） | Mapboxクライアント |

---

## 7. 公式ドキュメント参照一覧

### FastAPI
- 基本: https://fastapi.tiangolo.com/
- Query Parameters: https://fastapi.tiangolo.com/tutorial/query-params/
- Dependencies: https://fastapi.tiangolo.com/tutorial/dependencies/
- Lifespan: https://fastapi.tiangolo.com/advanced/events/
- Response Model: https://fastapi.tiangolo.com/tutorial/response-model/

### Pydantic
- Models: https://docs.pydantic.dev/latest/concepts/models/
- Fields: https://docs.pydantic.dev/latest/concepts/fields/
- Aliases: https://docs.pydantic.dev/latest/concepts/alias/
- Generic Models: https://docs.pydantic.dev/latest/concepts/models/#generic-models

### NetworkX
- A* Algorithm: https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.shortest_paths.astar.astar_path.html
- subgraph_view: https://networkx.org/documentation/stable/reference/classes/generated/networkx.classes.graphviews.subgraph_view.html

### 外部API
- GBFS仕様: https://gbfs.org/documentation/reference/
- Mapbox Map Matching: https://docs.mapbox.com/api/navigation/map-matching/
- Mapbox Directions: https://docs.mapbox.com/api/navigation/directions/

### その他
- httpx: https://www.python-httpx.org/async/
- Haversine: https://pypi.org/project/haversine/
- OSMnx: https://osmnx.readthedocs.io/
- Shapely (Douglas-Peucker): https://shapely.readthedocs.io/en/stable/reference/shapely.simplify.html

---

## 付録A: エラーコード一覧

| コード | 説明 |
|--------|------|
| `INVALID_COORDINATES` | 座標形式が不正 |
| `OUT_OF_SERVICE_AREA` | 京都市外の座標 |
| `NO_ROUTE_FOUND` | ルートが見つからない |
| `NO_PARKING_FOUND` | 駐輪場が見つからない |
| `NO_PORT_AVAILABLE` | 利用可能なポートがない |
| `MAPBOX_API_ERROR` | Mapbox APIエラー |
| `GBFS_API_ERROR` | GBFS APIエラー |

---

## 付録B: 重み計算式

```
safe_factor = 1.0 - (safety × 0.03)    # 0.97 ~ 0.70
normal_factor = 1.0 + (safety × 0.2)   # 1.2 ~ 3.0

if is_safe:
    cost = length × safe_factor
else:
    cost = length × normal_factor
```

| safety | safe_factor | normal_factor | 100m安全道 | 100m通常道 |
|--------|-------------|---------------|-----------|-----------|
| 1 | 0.97 | 1.2 | 97m | 120m |
| 5 | 0.85 | 2.0 | 85m | 200m |
| 10 | 0.70 | 3.0 | 70m | 300m |

---

## 付録C: シェアサイクルルート計算

`calculate_share_cycle_route()` の戻り値:

| キー | 型 | 説明 |
|------|-----|------|
| `borrow_port` | Port | レンタルポート（自転車を借りる場所） |
| `return_port` | Port | 返却ポート（自転車を返す場所） |
| `walk_to_port` | float | 出発地→レンタルポートの徒歩距離(m) |
| `bicycle_route` | RouteResult | レンタルポート→返却ポートの自転車ルート |
| `walk_from_port` | float | 返却ポート→目的地の徒歩距離(m) |
| `total_distance` | float | 総距離(m) |
| `total_duration` | float | 総所要時間(秒) |

ポート選択ロジック:
- `borrow_port`: 出発地から最寄りの空き自転車があるポート
- `return_port`: 目的地から最寄りの空きドックがあるポート

---

## 付録D: データフロー図

```
┌─────────────────────────────────────────────────────────────┐
│                        起動時                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  app/data/graph/kyoto_bike_graph.pkl ──→ app.state.graph   │
│                                              │              │
│  app/data/parkings.py (PARKINGS) ──→ app.state.parkings    │
│                                              │              │
│                                              ▼              │
│                                    RouteCalculator          │
│                                    (graph + parkings)       │
│                                              │              │
│                                              ▼              │
│                                    app.state.route_calculator│
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      リクエスト時                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  GET /api/route                                             │
│       │                                                     │
│       ▼                                                     │
│  route_calculator.calculate_*()                             │
│       │                                                     │
│       ├──→ graph（A*探索）                                  │
│       │                                                     │
│       ├──→ parkings（最寄り駐輪場検索）                      │
│       │                                                     │
│       └──→ mapbox_client（音声指示取得）                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```