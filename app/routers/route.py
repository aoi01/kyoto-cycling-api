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

async def _get_voice_instructions(
    origin: tuple[float, float],
    destination: tuple[float, float],
    coordinates: list[list[float]],
    mapbox_client: MapboxClient,
) -> tuple[list[VoiceInstruction], Optional[list[list[float]]]]:
    """
    Mapbox Directions APIで音声指示を取得

    従来のMap Matching APIではなくDirections APIを使用。
    始点と終点のみを送信し、Mapboxにルート計算と音声指示生成を任せる。

    これにより:
    - 数千座標を送る必要がなくなる
    - 「○つ目の目的地に到着しました」という不要な指示が出ない
    - APIリクエストが軽量化される

    Args:
        origin: 始点 (経度, 緯度)
        destination: 終点 (経度, 緯度)
        coordinates: 自前グラフで計算したルート座標（参考用、経由地抽出に使用可能）
        mapbox_client: Mapboxクライアント

    Returns:
        (音声指示リスト, Mapboxが返したルート座標リスト)
    """
    try:
        # Directions APIを使用（始点と終点のみ）
        # 注: 自前グラフの安全ルートとMapboxのルートは異なる可能性がある
        # 音声指示はMapboxのルートに基づくが、地図表示は自前ルートを使用
        instructions, mapbox_coords = await mapbox_client.get_directions(
            origin=origin,
            destination=destination,
            waypoints=None,  # 経由地なし（始点→終点の直接ルート）
            profile="cycling"
        )

        return instructions, mapbox_coords

    except Exception as e:
        print(f"Directions API failed: {e}")
        return [], None
