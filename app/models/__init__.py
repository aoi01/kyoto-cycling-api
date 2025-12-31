"""
app/models/__init__.py

モデルパッケージ

すべてのモデルをこのパッケージからインポート可能にする。

使用例:
    from app.models import ApiResponse, RouteData, Port, Parking
"""
from .common import (
    ApiResponse,
    ErrorDetail,
    GeoJSONPoint,
    GeoJSONLineString,
    create_success_response,
    create_error_response,
)
from .route import (
    TransportMode,
    SegmentType,
    PointType,
    RoutePoint,
    VoiceInstruction,
    RouteGeometry,
    RouteSegment,
    RouteSummary,
    RouteData,
)
from .port import (
    Port,
    PortsData,
    GBFSStationInfo,
    GBFSStationStatus,
)
from .parking import (
    Parking,
    ParkingsData,
)
__all__ = [
    # common
    "ApiResponse",
    "ErrorDetail",
    "GeoJSONPoint",
    "GeoJSONLineString",
    "create_success_response",
    "create_error_response",
    # route
    "TransportMode",
    "SegmentType",
    "PointType",
    "RoutePoint",
    "VoiceInstruction",
    "RouteGeometry",
    "RouteSegment",
    "RouteSummary",
    "RouteData",
    # port
    "Port",
    "PortsData",
    "GBFSStationInfo",
    "GBFSStationStatus",
    # parking
    "Parking",
    "ParkingsData",
]