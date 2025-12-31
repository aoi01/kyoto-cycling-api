"""
app/routers/ports.py

シェアサイクルポートAPIエンドポイント

GET /api/ports - ポート一覧取得

公式ドキュメント:
- GBFS仕様: https://gbfs.org/documentation/reference/
"""
from typing import Annotated, Optional
from fastapi import APIRouter, Query, Depends

from app.models import (
    ApiResponse,
    PortsData,
    create_success_response,
    create_error_response,
)
from app.services.gbfs_client import GBFSClient


# =============================================================================
# ルーター定義
# =============================================================================

router = APIRouter(prefix="/api", tags=["ports"])


# =============================================================================
# 依存性注入
# =============================================================================

def get_gbfs_client():
    """GBFSクライアントの依存性注入"""
    from app.main import app
    return app.state.gbfs_client


# =============================================================================
# エンドポイント
# =============================================================================

@router.get(
    "/ports",
    response_model=ApiResponse[PortsData],
    summary="ポート一覧取得",
    description="""
シェアサイクルポートの一覧を取得。

## 事業者

- `docomo`: ドコモ・バイクシェア
- `hellocycling`: HELLO CYCLING

## フィルタリング

- `near`: 中心座標を指定すると、その地点から近い順にソート
- `radius`: nearからの半径（メートル）
- `minBikes`: 最低空き台数
- `minDocks`: 最低空きドック数
    """,
)
async def get_ports(
    operators: Annotated[str, Query(
        description="事業者（カンマ区切り）",
        examples=["docomo", "hellocycling,docomo"],
    )],
    near: Annotated[Optional[str], Query(
        pattern=r"^-?\d+\.?\d*,-?\d+\.?\d*$",
        description="中心座標 '経度,緯度'（指定時は距離でソート）",
        examples=["135.7588,34.9858"],
    )] = None,
    radius: Annotated[int, Query(
        ge=100,
        le=5000,
        description="nearからの半径（メートル）",
    )] = 500,
    minBikes: Annotated[int, Query(
        ge=0,
        description="最低空き台数",
    )] = 1,
    minDocks: Annotated[int, Query(
        ge=0,
        description="最低空きドック数",
    )] = 1,
    gbfs_client: GBFSClient = Depends(get_gbfs_client),
) -> ApiResponse[PortsData]:
    """
    ポート一覧取得API
    
    GBFS station_information と station_status を統合して返却。
    """
    try:
        # 事業者リストをパース
        operator_list = [op.strip() for op in operators.split(",")]
        
        # near座標をパース
        near_coords = None
        if near:
            try:
                parts = near.split(",")
                near_coords = (float(parts[0]), float(parts[1]))
            except (ValueError, IndexError):
                return create_error_response(
                    "INVALID_COORDINATES",
                    "near座標の形式が不正です"
                )
        
        # ポート取得
        ports_data = await gbfs_client.get_ports(
            operators=operator_list,
            near=near_coords,
            radius=radius,
            min_bikes=minBikes,
            min_docks=minDocks,
        )
        
        return create_success_response(ports_data)
    
    except Exception as e:
        print(f"Ports API error: {e}")
        return create_error_response("GBFS_API_ERROR", f"GBFS APIエラー: {str(e)}")