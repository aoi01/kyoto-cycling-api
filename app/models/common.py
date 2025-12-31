"""
app/models/common.py

共通モデル定義

このファイルは、API全体で使用される共通のデータモデルを定義します。
FastAPIとPydanticを使用した型安全なモデルを提供します。

公式ドキュメント:
- Pydantic V2: https://docs.pydantic.dev/latest/
- FastAPI Response Model: https://fastapi.tiangolo.com/tutorial/response-model/
- Generic Types: https://docs.pydantic.dev/latest/concepts/models/#generic-models
"""
from typing import TypeVar, Generic, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime


# =============================================================================
# ジェネリック型変数
# =============================================================================

# TypeVarを使用してジェネリック型を定義
# 参照: https://docs.pydantic.dev/latest/concepts/models/#generic-models
T = TypeVar('T')


# =============================================================================
# エラーモデル
# =============================================================================

class ErrorDetail(BaseModel):
    """
    エラー詳細モデル
    
    Attributes:
        code (str): エラーコード（例: "INVALID_COORDINATES", "NO_ROUTE_FOUND"）
        message (str): ユーザー向けエラーメッセージ
    
    エラーコード一覧:
        - INVALID_COORDINATES: 座標形式が不正
        - OUT_OF_SERVICE_AREA: 京都市外の座標
        - NO_ROUTE_FOUND: ルートが見つからない
        - NO_PARKING_FOUND: 駐輪場が見つからない
        - NO_PORT_AVAILABLE: 利用可能なポートがない
        - MAPBOX_API_ERROR: Mapbox APIエラー
        - GBFS_API_ERROR: GBFS APIエラー
        - INTERNAL_ERROR: 内部エラー
    """
    code: str = Field(
        ...,
        description="エラーコード",
        examples=["INVALID_COORDINATES", "NO_ROUTE_FOUND"]
    )
    message: str = Field(
        ...,
        description="ユーザー向けエラーメッセージ",
        examples=["座標形式が不正です", "ルートが見つかりませんでした"]
    )


# =============================================================================
# 統一APIレスポンスモデル
# =============================================================================

class ApiResponse(BaseModel, Generic[T]):
    """
    統一APIレスポンスモデル（ジェネリック型）
    
    すべてのAPIエンドポイントで使用する統一的なレスポンス形式。
    成功時はdataにデータを、失敗時はerrorにエラー詳細を格納。
    
    設計根拠:
    - フロントエンドで統一的なエラーハンドリングが可能
    - success フラグで成功/失敗を明確に判定
    - Generic[T] により型安全性を確保
    
    参照: https://fastapi.tiangolo.com/tutorial/response-model/
    「response_model パラメータを使用して、レスポンスの型を指定」
    
    Attributes:
        success (bool): リクエスト成功フラグ
        data (Optional[T]): 成功時のデータ（型パラメータT）
        error (Optional[ErrorDetail]): 失敗時のエラー詳細
    
    使用例:
        # 成功レスポンス
        ApiResponse(success=True, data=RouteData(...))
        
        # エラーレスポンス
        ApiResponse(success=False, error=ErrorDetail(code="NO_ROUTE_FOUND", message="..."))
    """
    success: bool = Field(
        ...,
        description="リクエスト成功フラグ"
    )
    data: Optional[T] = Field(
        default=None,
        description="成功時のレスポンスデータ"
    )
    error: Optional[ErrorDetail] = Field(
        default=None,
        description="失敗時のエラー詳細"
    )
    
    class Config:
        """Pydantic設定"""
        # JSONスキーマで具体的な型を表示
        # 参照: https://docs.pydantic.dev/latest/concepts/json_schema/
        json_schema_extra = {
            "examples": [
                {
                    "success": True,
                    "data": {"message": "成功レスポンス例"},
                    "error": None
                },
                {
                    "success": False,
                    "data": None,
                    "error": {"code": "NO_ROUTE_FOUND", "message": "ルートが見つかりませんでした"}
                }
            ]
        }


# =============================================================================
# GeoJSON関連モデル
# =============================================================================

class GeoJSONPoint(BaseModel):
    """
    GeoJSON Point型
    
    GeoJSON仕様: https://datatracker.ietf.org/doc/html/rfc7946#section-3.1.2
    
    Attributes:
        type (str): 常に "Point"
        coordinates (list[float]): [経度, 緯度]
    """
    type: Literal["Point"] = "Point"
    coordinates: list[float] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="[経度, 緯度]",
        examples=[[135.7588, 34.9858]]
    )


class GeoJSONLineString(BaseModel):
    """
    GeoJSON LineString型
    
    ルートのジオメトリを表現するために使用。
    
    GeoJSON仕様: https://datatracker.ietf.org/doc/html/rfc7946#section-3.1.4
    
    Attributes:
        type (str): 常に "LineString"
        coordinates (list[list[float]]): [[経度, 緯度], ...]の配列
    """
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]] = Field(
        ...,
        min_length=2,
        description="座標配列 [[経度, 緯度], ...]",
        examples=[[[135.7588, 34.9858], [135.7500, 35.0000], [135.7482, 35.0142]]]
    )


# =============================================================================
# ヘルパー関数
# =============================================================================

def create_success_response(data: T) -> ApiResponse[T]:
    """
    成功レスポンスを作成するヘルパー関数
    
    Args:
        data: レスポンスデータ
    
    Returns:
        ApiResponse[T]: 成功レスポンス
    """
    return ApiResponse(success=True, data=data)


def create_error_response(code: str, message: str) -> ApiResponse:
    """
    エラーレスポンスを作成するヘルパー関数
    
    Args:
        code: エラーコード
        message: エラーメッセージ
    
    Returns:
        ApiResponse: エラーレスポンス
    """
    return ApiResponse(
        success=False,
        error=ErrorDetail(code=code, message=message)
    )