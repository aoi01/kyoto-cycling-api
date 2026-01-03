"""
app/routers/route.py

ルート検索APIエンドポイント

GET /api/route - ルート検索

公式ドキュメント:
- FastAPI Query Parameters: https://fastapi.tiangolo.com/tutorial/query-params/
- FastAPI Dependencies: https://fastapi.tiangolo.com/tutorial/dependencies/
- Pydantic Validation: https://docs.pydantic.dev/latest/concepts/validators/
"""
from typing import Annotated, Optional
from fastapi import APIRouter, Query, Depends, HTTPException

from app.models import (
    ApiResponse,
    ErrorDetail,
    RouteData,
    RouteSegment,
    RouteSummary,
    RoutePoint,
    RouteGeometry,
    VoiceInstruction,
    TransportMode,
    SegmentType,
    PointType,
    GeoJSONLineString,
    create_success_response,
    create_error_response,
)
from app.services.route_calculator import RouteCalculator, RouteResult
from app.services.gbfs_client import GBFSClient
from app.services.mapbox_client import MapboxClient


# =============================================================================
# ルーター定義
# =============================================================================

router = APIRouter(prefix="/api", tags=["route"])


# =============================================================================
# 依存性注入
# =============================================================================

def get_route_calculator():
    """
    RouteCalculatorの依存性注入

    FastAPIのDependsを使用して、RouteCalculatorインスタンスを注入。
    実際のインスタンスはapp.stateに格納されている。

    参照: https://fastapi.tiangolo.com/tutorial/dependencies/
    「You can use Depends to inject dependencies into your path operation functions」
    """
    from app.main import app
    return app.state.route_calculator


def get_gbfs_client():
    """GBFSクライアントの依存性注入"""
    from app.main import app
    return app.state.gbfs_client


def get_mapbox_client():
    """Mapboxクライアントの依存性注入"""
    from app.main import app
    return app.state.mapbox_client


# =============================================================================
# バリデーション
# =============================================================================

# 京都市のバウンディングボックス
KYOTO_BBOX = {
    "min_lat": 34.85,
    "max_lat": 35.15,
    "min_lon": 135.60,
    "max_lon": 135.90,
}


def parse_coordinates(coord_str: str) -> tuple[float, float]:
    """
    座標文字列をパース

    Args:
        coord_str: "経度,緯度" 形式の文字列

    Returns:
        (経度, 緯度) のタプル

    Raises:
        ValueError: パース失敗
    """
    try:
        parts = coord_str.split(",")
        if len(parts) != 2:
            raise ValueError("座標は '経度,緯度' の形式で指定してください")
        lon = float(parts[0])
        lat = float(parts[1])
        return lon, lat
    except (ValueError, IndexError) as e:
        raise ValueError(f"座標形式が不正です: {coord_str}")


def is_in_kyoto(lon: float, lat: float) -> bool:
    """京都市内かどうか判定"""
    return (KYOTO_BBOX["min_lon"] <= lon <= KYOTO_BBOX["max_lon"] and
            KYOTO_BBOX["min_lat"] <= lat <= KYOTO_BBOX["max_lat"])


# =============================================================================
# エンドポイント
# =============================================================================

@router.get(
    "/route",
    response_model=ApiResponse[RouteData],
    summary="ルート検索",
    description="""
出発地から目的地への自転車ルートを計算し、音声ナビ指示付きで返却。

## ユースケース

1. **UC-1**: 自分の自転車で観光地へ（駐輪場案内あり）
   - `mode=my-cycle`, `needParking=true`

2. **UC-2**: 自分の自転車で観光地へ（駐輪場案内なし）
   - `mode=my-cycle`, `needParking=false`

3. **UC-3**: シェアサイクルで観光地へ
   - `mode=share-cycle`, `operators=docomo,hellocycling`

## 安全度パラメータ

- `safety=1`: 最短距離重視
- `safety=5`: バランス
- `safety=10`: 安全最優先（安全道を大幅に優遇）
    """,
    responses={
        200: {"description": "成功"},
        400: {"description": "パラメータエラー"},
        404: {"description": "ルートが見つからない"},
        502: {"description": "外部APIエラー"},
    },
)
async def search_route(
    # --- 必須パラメータ ---
    origin: Annotated[str, Query(
        pattern=r"^-?\d+\.?\d*,-?\d+\.?\d*$",
        description="出発地座標 '経度,緯度'",
        examples=["135.7588,34.9858"],
    )],
    destination: Annotated[str, Query(
        pattern=r"^-?\d+\.?\d*,-?\d+\.?\d*$",
        description="目的地座標 '経度,緯度'",
        examples=["135.7482,35.0142"],
    )],
    mode: Annotated[TransportMode, Query(
        description="移動モード",
    )],
    safety: Annotated[int, Query(
        ge=1,
        le=10,
        description="安全指数 1-10",
    )],
    # --- オプションパラメータ ---
    needParking: Annotated[bool, Query(
        description="駐輪場案内が必要か（my-cycle時のみ有効）",
    )] = False,
    operators: Annotated[Optional[str], Query(
        description="シェアサイクル事業者（カンマ区切り、share-cycle時のみ有効）",
        examples=["docomo", "hellocycling,docomo"],
    )] = None,
    # --- 依存性注入 ---
    route_calculator: RouteCalculator = Depends(get_route_calculator),
    gbfs_client: GBFSClient = Depends(get_gbfs_client),
    mapbox_client: MapboxClient = Depends(get_mapbox_client),
) -> ApiResponse[RouteData]:
    """
    ルート検索API

    処理フロー:
    1. 座標パース・バリデーション
    2. モードに応じたルート計算
    3. Mapbox Map Matchingで音声指示取得
    4. レスポンス整形
    """
    try:
        # === 1. 座標パース ===
        origin_lon, origin_lat = parse_coordinates(origin)
        dest_lon, dest_lat = parse_coordinates(destination)

        # === 2. 京都市内チェック ===
        if not is_in_kyoto(origin_lon, origin_lat):
            return create_error_response(
                "OUT_OF_SERVICE_AREA",
                "出発地が京都市外です"
            )
        if not is_in_kyoto(dest_lon, dest_lat):
            return create_error_response(
                "OUT_OF_SERVICE_AREA",
                "目的地が京都市外です"
            )

        origin_coords = (origin_lon, origin_lat)
        dest_coords = (dest_lon, dest_lat)

        # === 3. モードに応じたルート計算 ===
        if mode == TransportMode.SHARE_CYCLE:
            # UC-3: シェアサイクルルート
            return await _handle_share_cycle_route(
                origin_coords, dest_coords, safety, operators,
                route_calculator, gbfs_client, mapbox_client
            )
        elif needParking:
            # UC-1: 駐輪場経由ルート
            return await _handle_parking_route(
                origin_coords, dest_coords, safety,
                route_calculator, mapbox_client
            )
        else:
            # UC-2: 直接ルート
            return await _handle_direct_route(
                origin_coords, dest_coords, safety,
                route_calculator, mapbox_client
            )

    except ValueError as e:
        return create_error_response("INVALID_COORDINATES", str(e))
    except Exception as e:
        print(f"Route search error: {e}")
        return create_error_response("INTERNAL_ERROR", f"内部エラー: {str(e)}")


# =============================================================================
# ルート計算ハンドラ
# =============================================================================

async def _handle_direct_route(
    origin: tuple[float, float],
    destination: tuple[float, float],
    safety: int,
    route_calculator: RouteCalculator,
    mapbox_client: MapboxClient,
) -> ApiResponse[RouteData]:
    """
    直接ルートを処理（UC-2）

    Args:
        origin: 出発地 (経度, 緯度)
        destination: 目的地 (経度, 緯度)
        safety: 安全度
        route_calculator: ルート計算サービス
        mapbox_client: Mapboxクライアント

    Returns:
        ApiResponse[RouteData]
    """
    try:
        # ルート計算
        result = route_calculator.calculate_direct_route(origin, destination, safety)

        # Directions APIで音声指示取得
        voice_instructions, matched_coords = await _get_voice_instructions(
            origin, destination, result.coordinates, mapbox_client
        )

        # セグメント作成
        segment = RouteSegment(
            type=SegmentType.BICYCLE,
            from_=RoutePoint(
                type=PointType.ORIGIN,
                coordinates=list(origin),
                name="現在地",
            ),
            to=RoutePoint(
                type=PointType.DESTINATION,
                coordinates=list(destination),
                name="目的地",
            ),
            route=RouteGeometry(
                geometry=GeoJSONLineString(coordinates=matched_coords or result.coordinates),
                distance=result.distance,
                duration=result.duration,
                safety_score=result.safety_score,
            ),
            voice_instructions=voice_instructions,
        )

        # レスポンス作成
        route_data = RouteData(
            segments=[segment],
            summary=RouteSummary(
                total_distance=result.distance,
                total_duration=result.duration,
                bicycle_distance=result.distance,
                walk_distance=0,
                average_safety_score=result.safety_score,
            ),
        )

        return create_success_response(route_data)

    except Exception as e:
        if "NetworkXNoPath" in str(e):
            return create_error_response("NO_ROUTE_FOUND", "ルートが見つかりませんでした")
        raise


async def _handle_parking_route(
    origin: tuple[float, float],
    destination: tuple[float, float],
    safety: int,
    route_calculator: RouteCalculator,
    mapbox_client: MapboxClient,
) -> ApiResponse[RouteData]:
    """
    駐輪場経由ルートを処理（UC-1）
    """
    try:
        # ルート計算
        result = route_calculator.calculate_route_with_parking(origin, destination, safety)

        parking = result['parking']
        bicycle_route = result['bicycle_route']

        # Directions APIで音声指示取得（origin → parking）
        parking_coords = (parking.coordinates[0], parking.coordinates[1])
        voice_instructions, matched_coords = await _get_voice_instructions(
            origin, parking_coords, bicycle_route.coordinates, mapbox_client
        )

        # セグメント作成
        segments = [
            # 自転車区間: origin → parking
            RouteSegment(
                type=SegmentType.BICYCLE,
                from_=RoutePoint(
                    type=PointType.ORIGIN,
                    coordinates=list(origin),
                    name="現在地",
                ),
                to=RoutePoint(
                    type=PointType.PARKING,
                    coordinates=parking.coordinates,
                    name=parking.name,
                    id=parking.id,
                    fee_description=parking.fee_description,
                ),
                route=RouteGeometry(
                    geometry=GeoJSONLineString(coordinates=matched_coords or bicycle_route.coordinates),
                    distance=bicycle_route.distance,
                    duration=bicycle_route.duration,
                    safety_score=bicycle_route.safety_score,
                ),
                voice_instructions=voice_instructions,
            ),
            # 徒歩区間: parking → destination
            RouteSegment(
                type=SegmentType.WALK,
                from_=RoutePoint(
                    type=PointType.PARKING,
                    coordinates=parking.coordinates,
                    name=parking.name,
                ),
                to=RoutePoint(
                    type=PointType.DESTINATION,
                    coordinates=list(destination),
                    name="目的地",
                ),
                route=RouteGeometry(
                    geometry=GeoJSONLineString(coordinates=[parking.coordinates, list(destination)]),
                    distance=result['walk_distance'],
                    duration=result['walk_duration'],
                    safety_score=None,
                ),
                voice_instructions=[],
            ),
        ]

        route_data = RouteData(
            segments=segments,
            summary=RouteSummary(
                total_distance=result['total_distance'],
                total_duration=result['total_duration'],
                bicycle_distance=bicycle_route.distance,
                walk_distance=result['walk_distance'],
                average_safety_score=bicycle_route.safety_score,
            ),
        )

        return create_success_response(route_data)

    except ValueError as e:
        return create_error_response("NO_PARKING_FOUND", str(e))
    except Exception as e:
        if "NetworkXNoPath" in str(e):
            return create_error_response("NO_ROUTE_FOUND", "ルートが見つかりませんでした")
        raise


async def _handle_share_cycle_route(
    origin: tuple[float, float],
    destination: tuple[float, float],
    safety: int,
    operators: Optional[str],
    route_calculator: RouteCalculator,
    gbfs_client: GBFSClient,
    mapbox_client: MapboxClient,
) -> ApiResponse[RouteData]:
    """
    シェアサイクルルートを処理（UC-3）
    """
    try:
        # 事業者リストをパース
        operator_list = operators.split(",") if operators else ["docomo"]

        # ポート情報取得
        ports_data = await gbfs_client.get_ports(operator_list)
        if not ports_data.ports:
            return create_error_response(
                "NO_PORT_AVAILABLE",
                "利用可能なポートが見つかりません"
            )

        # ルート計算
        result = route_calculator.calculate_share_cycle_route(
            origin, destination, safety, ports_data.ports
        )

        borrow_port = result['borrow_port']
        return_port = result['return_port']
        bicycle_route = result['bicycle_route']

        # Directions APIで音声指示取得（borrow_port → return_port）
        borrow_coords = (borrow_port.coordinates[0], borrow_port.coordinates[1])
        return_coords = (return_port.coordinates[0], return_port.coordinates[1])
        voice_instructions, matched_coords = await _get_voice_instructions(
            borrow_coords, return_coords, bicycle_route.coordinates, mapbox_client
        )

        # セグメント作成
        segments = [
            # 徒歩区間: origin → borrow_port
            RouteSegment(
                type=SegmentType.WALK,
                from_=RoutePoint(
                    type=PointType.ORIGIN,
                    coordinates=list(origin),
                    name="現在地",
                ),
                to=RoutePoint(
                    type=PointType.PORT,
                    coordinates=borrow_port.coordinates,
                    name=borrow_port.name,
                    id=borrow_port.id,
                ),
                route=RouteGeometry(
                    geometry=GeoJSONLineString(coordinates=[list(origin), borrow_port.coordinates]),
                    distance=result['walk_to_port'],
                    duration=result['walk_to_port'] / 1.4,
                    safety_score=None,
                ),
                voice_instructions=[],
            ),
            # 自転車区間: borrow_port → return_port
            RouteSegment(
                type=SegmentType.BICYCLE,
                from_=RoutePoint(
                    type=PointType.PORT,
                    coordinates=borrow_port.coordinates,
                    name=borrow_port.name,
                ),
                to=RoutePoint(
                    type=PointType.PORT,
                    coordinates=return_port.coordinates,
                    name=return_port.name,
                    id=return_port.id,
                ),
                route=RouteGeometry(
                    geometry=GeoJSONLineString(coordinates=matched_coords or bicycle_route.coordinates),
                    distance=bicycle_route.distance,
                    duration=bicycle_route.duration,
                    safety_score=bicycle_route.safety_score,
                ),
                voice_instructions=voice_instructions,
            ),
            # 徒歩区間: return_port → destination
            RouteSegment(
                type=SegmentType.WALK,
                from_=RoutePoint(
                    type=PointType.PORT,
                    coordinates=return_port.coordinates,
                    name=return_port.name,
                ),
                to=RoutePoint(
                    type=PointType.DESTINATION,
                    coordinates=list(destination),
                    name="目的地",
                ),
                route=RouteGeometry(
                    geometry=GeoJSONLineString(coordinates=[return_port.coordinates, list(destination)]),
                    distance=result['walk_from_port'],
                    duration=result['walk_from_port'] / 1.4,
                    safety_score=None,
                ),
                voice_instructions=[],
            ),
        ]

        route_data = RouteData(
            segments=segments,
            summary=RouteSummary(
                total_distance=result['total_distance'],
                total_duration=result['total_duration'],
                bicycle_distance=bicycle_route.distance,
                walk_distance=result['walk_to_port'] + result['walk_from_port'],
                average_safety_score=bicycle_route.safety_score,
            ),
        )

        return create_success_response(route_data)

    except ValueError as e:
        return create_error_response("NO_PORT_AVAILABLE", str(e))
    except Exception as e:
        if "NetworkXNoPath" in str(e):
            return create_error_response("NO_ROUTE_FOUND", "ルートが見つかりませんでした")
        raise


# =============================================================================
# ヘルパー関数
# =============================================================================

import math


def _calculate_bearing(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    2点間の方位角（bearing）を計算（度数法、0-360）

    北を0度として時計回りに角度を返す。

    Args:
        lon1, lat1: 始点の経度・緯度
        lon2, lat2: 終点の経度・緯度

    Returns:
        方位角（0-360度）
    """
    # ラジアンに変換
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lon = math.radians(lon2 - lon1)

    x = math.sin(delta_lon) * math.cos(lat2_rad)
    y = (math.cos(lat1_rad) * math.sin(lat2_rad) -
         math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon))

    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def _angle_difference(bearing1: float, bearing2: float) -> float:
    """
    2つの方位角の差を計算（0-180度）

    Args:
        bearing1, bearing2: 方位角（0-360度）

    Returns:
        角度差（0-180度）
    """
    diff = abs(bearing1 - bearing2)
    return min(diff, 360 - diff)


def _extract_turn_points(
    coordinates: list[list[float]],
    angle_threshold: float = 30.0,
    max_waypoints: int = 23,
) -> list[tuple[float, float]]:
    """
    ルート座標から曲がり角（ターンポイント）を抽出

    連続する座標間の進行方向を計算し、大きく方向が変わる点を抽出する。
    これにより、数百の座標から重要な経由地のみを取り出せる。

    アルゴリズム:
    1. 連続する3点 (A, B, C) を見る
    2. A→Bの方位角と B→Cの方位角を計算
    3. 角度差が閾値を超えたらBは曲がり角
    4. 曲がり角が多すぎる場合、閾値を上げて再抽出

    Args:
        coordinates: ルート座標 [[経度, 緯度], ...]
        angle_threshold: 曲がり角と判定する角度差の閾値（度）
        max_waypoints: 最大経由地数（Mapbox APIの制限は23）

    Returns:
        曲がり角の座標リスト [(経度, 緯度), ...]
    """
    if len(coordinates) < 3:
        return []

    turn_points = []

    for i in range(1, len(coordinates) - 1):
        prev = coordinates[i - 1]
        curr = coordinates[i]
        next_ = coordinates[i + 1]

        # 方位角を計算
        bearing1 = _calculate_bearing(prev[0], prev[1], curr[0], curr[1])
        bearing2 = _calculate_bearing(curr[0], curr[1], next_[0], next_[1])

        # 角度差が閾値を超えたら曲がり角
        angle_diff = _angle_difference(bearing1, bearing2)
        if angle_diff >= angle_threshold:
            turn_points.append((curr[0], curr[1], angle_diff))

    # 曲がり角が多すぎる場合、角度差の大きい順にソートして上位を選択
    if len(turn_points) > max_waypoints:
        # 角度差でソート（大きい順）
        turn_points.sort(key=lambda x: x[2], reverse=True)
        turn_points = turn_points[:max_waypoints]
        # 元のルート順に並び替え
        turn_points_set = {(tp[0], tp[1]) for tp in turn_points}
        turn_points = []
        for coord in coordinates:
            if (coord[0], coord[1]) in turn_points_set:
                turn_points.append((coord[0], coord[1]))
                if len(turn_points) >= max_waypoints:
                    break
    else:
        turn_points = [(tp[0], tp[1]) for tp in turn_points]

    return turn_points


def _filter_voice_instructions(
    instructions: list[VoiceInstruction],
    min_distance_between: float = 50.0,
) -> list[VoiceInstruction]:
    """
    音声指示をフィルタリング

    Map Matching APIからの音声指示から不要なものを除去し、
    実用的なナビゲーション指示のみを残す。

    フィルタリング対象:
    1. 「○つ目の目的地」→ すべて除去
    2. 「目的地に到着しました」→ 最後のもののみ残す
    3. 重複する指示 → 距離が近い（50m以内）ものを除去
    4. 「その先」を含む複合指示 → 分割して最初の部分のみ

    Args:
        instructions: 元の音声指示リスト
        min_distance_between: 指示間の最小距離（メートル）

    Returns:
        フィルタリング後の音声指示リスト
    """
    if not instructions:
        return []

    # キーワード定義
    waypoint_keywords = ["つ目の目的地"]
    arrival_keywords = ["目的地に到着", "まもなく目的地"]

    # 到着指示とそれ以外を分離
    arrival_instructions = []
    other_instructions = []

    for inst in instructions:
        announcement = inst.announcement

        # 「○つ目の目的地」は完全に除去
        if any(kw in announcement for kw in waypoint_keywords):
            continue

        # 「その先」で分割し、最初の部分のみ使用
        if "その先" in announcement:
            parts = announcement.split("その先")
            announcement = parts[0].strip().rstrip("。")
            if not announcement:
                continue
            inst = VoiceInstruction(
                distance_along_geometry=inst.distance_along_geometry,
                announcement=announcement,
            )

        # 到着関連の指示を分離
        if any(kw in announcement for kw in arrival_keywords):
            arrival_instructions.append(inst)
        else:
            other_instructions.append(inst)

    # 重複除去：距離が近い指示を統合
    filtered = []
    last_distance = -min_distance_between * 2  # 最初の指示は必ず含める

    for inst in other_instructions:
        if inst.distance_along_geometry - last_distance >= min_distance_between:
            filtered.append(inst)
            last_distance = inst.distance_along_geometry

    # 最後の到着指示のみを残す
    final_arrival = []
    if arrival_instructions:
        max_distance = max(inst.distance_along_geometry for inst in arrival_instructions)
        # 最大距離の到着指示を1つだけ残す
        for inst in arrival_instructions:
            if inst.distance_along_geometry >= max_distance - 100:
                final_arrival.append(inst)
                break

    # 結合して距離順にソート
    result = filtered + final_arrival
    result.sort(key=lambda x: x.distance_along_geometry)

    return result


def _simplify_coordinates(
    coordinates: list[list[float]],
    tolerance: float = 0.0001,
    max_count: int = 100,
) -> list[tuple[float, float]]:
    """
    Douglas-Peuckerアルゴリズムでルート座標を簡略化

    shapely.LineString.simplify() を使用して、ルートの形状を保ちながら
    座標点数を削減する。

    Douglas-Peuckerアルゴリズム:
    - 始点と終点を結ぶ直線から最も離れた点を見つける
    - その距離がtolerance以下なら中間点を全て削除
    - tolerance以上なら、その点で分割して再帰的に処理

    Args:
        coordinates: 座標リスト [[経度, 緯度], ...]
        tolerance: 簡略化の許容誤差（度数）
                   0.0001度 ≈ 約11m（緯度による）
                   0.00005度 ≈ 約5m
        max_count: 最大座標数（API制限用）

    Returns:
        簡略化された座標リスト [(経度, 緯度), ...]
    """
    from shapely.geometry import LineString

    if len(coordinates) < 3:
        return [(c[0], c[1]) for c in coordinates]

    # LineStringを作成
    line = LineString(coordinates)

    # Douglas-Peuckerで簡略化
    simplified = line.simplify(tolerance, preserve_topology=True)

    # 座標を抽出
    result = list(simplified.coords)

    # まだ多すぎる場合は、toleranceを上げて再度簡略化
    current_tolerance = tolerance
    while len(result) > max_count and current_tolerance < 0.01:
        current_tolerance *= 2
        simplified = line.simplify(current_tolerance, preserve_topology=True)
        result = list(simplified.coords)

    # それでも多い場合は均等サンプリングにフォールバック
    if len(result) > max_count:
        step = (len(result) - 1) / (max_count - 1)
        sampled = []
        for i in range(max_count - 1):
            idx = int(i * step)
            sampled.append(result[idx])
        sampled.append(result[-1])
        result = sampled

    return result


async def _get_voice_instructions(
    origin: tuple[float, float],
    destination: tuple[float, float],
    coordinates: list[list[float]],
    mapbox_client: MapboxClient,
) -> tuple[list[VoiceInstruction], Optional[list[list[float]]]]:
    """
    Mapbox Map Matching APIで音声指示を取得

    自前グラフで計算したルート座標をダウンサンプリングして
    Map Matching APIに送信する。

    Map Matching APIのwaypointsパラメータで始点・終点のみを指定することで、
    中間座標はルート形状の参考としてのみ使用され、
    「○つ目の目的地に到着しました」という不要な指示が出ない。

    処理フロー:
    1. ルート座標をダウンサンプリング（最大100点）
    2. Map Matching APIに送信（waypoints=始点・終点のみ）
    3. 音声指示から中間到着指示をフィルタリング

    Args:
        origin: 始点 (経度, 緯度)
        destination: 終点 (経度, 緯度)
        coordinates: 自前グラフで計算したルート座標
        mapbox_client: Mapboxクライアント

    Returns:
        (音声指示リスト, Mapboxが返したルート座標リスト)
    """
    try:
        # Douglas-Peuckerで座標を簡略化
        simplified_coords = _simplify_coordinates(
            coordinates,
            tolerance=0.0001,  # 約11m
            max_count=100,     # Map Matching API制限
        )

        print(f"Coordinates: {len(coordinates)} -> {len(simplified_coords)} (simplified)")

        # Map Matching APIを使用
        # waypointsパラメータは mapbox_client.map_match 内部で
        # 始点・終点のみに設定される
        geometry, instructions, distance, duration = await mapbox_client.map_match(
            coordinates=simplified_coords,
            profile="cycling"
        )

        # 中間到着指示をフィルタリング
        filtered_instructions = _filter_voice_instructions(instructions)

        return filtered_instructions, geometry.coordinates

    except Exception as e:
        print(f"Map Matching API failed: {e}")
        return [], None
