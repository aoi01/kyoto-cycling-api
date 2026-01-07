"""
app/models/route.py

ルート検索関連のモデル定義

このファイルは、ルート検索APIで使用するデータモデルを定義します。
セグメント（区間）、ポイント（地点）、ジオメトリ、音声指示などを含みます。

公式ドキュメント:
- Pydantic Field: https://docs.pydantic.dev/latest/concepts/fields/
- Pydantic Aliases: https://docs.pydantic.dev/latest/concepts/alias/
- Enum: https://docs.python.org/3/library/enum.html
"""
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field
from .common import GeoJSONLineString


# =============================================================================
# 列挙型（Enum）
# =============================================================================

class TransportMode(str, Enum):
    """
    移動モード

    APIクエリパラメータ mode で使用。
    str を継承することで、JSONシリアライズ時に文字列として出力。

    参照: https://docs.pydantic.dev/latest/concepts/types/#enums-and-choices

    Values:
        MY_CYCLE: 自分の自転車を使用
        SHARE_CYCLE: シェアサイクルを使用
    """
    MY_CYCLE = "my-cycle"
    SHARE_CYCLE = "share-cycle"


class SegmentType(str, Enum):
    """
    セグメント種別

    ルートの各区間の移動手段を表す。

    Values:
        WALK: 徒歩区間
        BICYCLE: 自転車区間
    """
    WALK = "walk"
    BICYCLE = "bicycle"


class PointType(str, Enum):
    """
    地点種別

    ルート上の各地点の種類を表す。

    Values:
        ORIGIN: 出発地
        DESTINATION: 目的地
        PARKING: 駐輪場
        PORT: シェアサイクルポート
    """
    ORIGIN = "origin"
    DESTINATION = "destination"
    PARKING = "parking"
    PORT = "port"


# =============================================================================
# 地点モデル
# =============================================================================

class RoutePoint(BaseModel):
    """
    ルート上の地点

    出発地、目的地、駐輪場、ポートなどの地点情報を表現。

    Attributes:
        type (PointType): 地点種別
        coordinates (list[float]): [経度, 緯度]
        name (str): 地点名称
        id (Optional[str]): 駐輪場/ポートのID（該当する場合のみ）
        fee_description (Optional[str]): 料金説明（駐輪場の場合のみ）

    使用例:
        # 出発地
        RoutePoint(type=PointType.ORIGIN, coordinates=[135.7588, 34.9858], name="現在地")

        # 駐輪場
        RoutePoint(
            type=PointType.PARKING,
            coordinates=[135.7590, 34.9850],
            name="京都駅前駐輪場",
            id="parking_001",
            fee_description="1日150円"
        )
    """
    type: PointType = Field(
        ...,
        description="地点種別"
    )
    coordinates: list[float] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="座標 [経度, 緯度]",
        examples=[[135.7588, 34.9858]]
    )
    name: str = Field(
        ...,
        description="地点名称",
        examples=["京都駅", "金閣寺", "京都駅前駐輪場"]
    )
    id: Optional[str] = Field(
        default=None,
        description="駐輪場またはポートのID",
        examples=["parking_001", "docomo_kyoto_001"]
    )
    # Pydantic v2では Field(alias=...) でJSONキー名を変更
    # 参照: https://docs.pydantic.dev/latest/concepts/alias/
    fee_description: Optional[str] = Field(
        default=None,
        alias="feeDescription",
        description="料金説明（駐輪場の場合）",
        examples=["1日150円", "2時間無料、以降100円/時間"]
    )

    model_config = {"populate_by_name": True}


# =============================================================================
# 音声指示モデル
# =============================================================================

class VoiceInstruction(BaseModel):
    """
    音声ナビゲーション指示

    Mapbox Map Matching API から取得した音声指示情報。
    ルートに沿って適切なタイミングで音声案内を提供するために使用。

    参照: https://docs.mapbox.com/api/navigation/map-matching/
    「voice_instructions=true でルートに沿った音声指示を取得」

    Attributes:
        distance_along_geometry (float): ルート開始点からの距離（メートル）
        announcement (str): 音声案内テキスト

    使用例:
        VoiceInstruction(
            distance_along_geometry=0,
            announcement="北へ進みます"
        )
        VoiceInstruction(
            distance_along_geometry=500,
            announcement="次の交差点を右に曲がります"
        )
    """
    # キャメルケースでJSONに出力
    distance_along_geometry: float = Field(
        ...,
        alias="distanceAlongGeometry",
        ge=0,
        description="ルート開始点からの距離（メートル）",
        examples=[0, 500, 1200]
    )
    announcement: str = Field(
        ...,
        description="音声案内テキスト",
        examples=["北へ進みます", "次の交差点を右に曲がります", "目的地に到着しました"]
    )

    model_config = {"populate_by_name": True}


# =============================================================================
# ルートジオメトリモデル
# =============================================================================

class RouteGeometry(BaseModel):
    """
    ルートジオメトリ情報

    ルートの形状（LineString）と、距離・所要時間・安全スコアを格納。

    Attributes:
        geometry (GeoJSONLineString): ルートの形状
        distance (float): 距離（メートル）
        duration (float): 所要時間（秒）
        safety_score (Optional[float]): 安全スコア（0-10）。徒歩区間はNull

    設計根拠:
        - 自転車区間のみ safety_score を持つ
        - 徒歩区間は安全道の概念がないため None
    """
    geometry: GeoJSONLineString = Field(
        ...,
        description="ルートの形状（GeoJSON LineString）"
    )
    distance: float = Field(
        ...,
        ge=0,
        description="距離（メートル）",
        examples=[2500.5]
    )
    duration: float = Field(
        ...,
        ge=0,
        description="所要時間（秒）",
        examples=[600.0]
    )
    safety_score: Optional[float] = Field(
        default=None,
        alias="safetyScore",
        ge=0,
        le=10,
        description="安全スコア（0-10）。自転車区間のみ。",
        examples=[7.5]
    )

    model_config = {"populate_by_name": True}


# =============================================================================
# ルートセグメントモデル
# =============================================================================

class RouteSegment(BaseModel):
    """
    ルートセグメント（区間）

    ルートを構成する各区間の情報。
    1つのルートは1つ以上のセグメントから構成される。

    例:
        - UC-2（直接ルート）: [bicycle区間] の1セグメント
        - UC-1（駐輪場経由）: [bicycle区間, walk区間] の2セグメント
        - UC-3（シェアサイクル）: [walk区間, bicycle区間, walk区間] の3セグメント

    Attributes:
        type (SegmentType): セグメント種別（walk/bicycle）
        from_ (RoutePoint): 出発地点（"from" はPython予約語のため from_ を使用）
        to (RoutePoint): 到着地点
        route (RouteGeometry): ルートジオメトリ
        voice_instructions (list[VoiceInstruction]): 音声指示リスト

    設計根拠:
        - "from" はPython予約語のため、from_ として定義し alias="from" で JSON 出力
        - 参照: https://docs.pydantic.dev/latest/concepts/alias/
    """
    type: SegmentType = Field(
        ...,
        description="セグメント種別（walk/bicycle）"
    )
    # "from" はPython予約語なので from_ を使用し、alias で JSON キー名を指定
    from_: RoutePoint = Field(
        ...,
        alias="from",
        description="出発地点"
    )
    to: RoutePoint = Field(
        ...,
        description="到着地点"
    )
    route: RouteGeometry = Field(
        ...,
        description="ルートジオメトリ"
    )
    voice_instructions: list[VoiceInstruction] = Field(
        default_factory=list,
        alias="voiceInstructions",
        description="音声指示リスト"
    )

    model_config = {"populate_by_name": True}


# =============================================================================
# ルートサマリーモデル
# =============================================================================

class RouteSummary(BaseModel):
    """
    ルートサマリー

    ルート全体の統計情報。

    Attributes:
        total_distance (float): 総距離（メートル）
        total_duration (float): 総所要時間（秒）
        bicycle_distance (float): 自転車区間の距離（メートル）
        walk_distance (float): 徒歩区間の距離（メートル）
        average_safety_score (Optional[float]): 平均安全スコア（0-10）
    """
    total_distance: float = Field(
        ...,
        alias="totalDistance",
        ge=0,
        description="総距離（メートル）",
        examples=[2800.0]
    )
    total_duration: float = Field(
        ...,
        alias="totalDuration",
        ge=0,
        description="総所要時間（秒）",
        examples=[720.0]
    )
    bicycle_distance: float = Field(
        ...,
        alias="bicycleDistance",
        ge=0,
        description="自転車区間の距離（メートル）",
        examples=[2500.0]
    )
    walk_distance: float = Field(
        ...,
        alias="walkDistance",
        ge=0,
        description="徒歩区間の距離（メートル）",
        examples=[300.0]
    )
    average_safety_score: Optional[float] = Field(
        default=None,
        alias="averageSafetyScore",
        ge=0,
        le=10,
        description="平均安全スコア（0-10）",
        examples=[7.5]
    )

    model_config = {"populate_by_name": True}


# =============================================================================
# ルートデータモデル（レスポンス）
# =============================================================================

class RouteData(BaseModel):
    """
    ルート検索レスポンスデータ

    GET /api/route のレスポンスに含まれるデータ。

    Attributes:
        segments (list[RouteSegment]): ルートセグメントのリスト
        summary (RouteSummary): ルートサマリー

    使用例:
        # UC-2: 直接ルート（1セグメント）
        RouteData(
            segments=[bicycle_segment],
            summary=RouteSummary(totalDistance=2500, ...)
        )

        # UC-1: 駐輪場経由（2セグメント）
        RouteData(
            segments=[bicycle_segment, walk_segment],
            summary=RouteSummary(totalDistance=2800, ...)
        )
    """
    segments: list[RouteSegment] = Field(
        ...,
        min_length=1,
        description="ルートセグメントのリスト（1つ以上）"
    )
    summary: RouteSummary = Field(
        ...,
        description="ルートサマリー"
    )
