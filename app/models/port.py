"""
app/models/port.py

シェアサイクルポート関連のモデル定義

GBFS (General Bikeshare Feed Specification) に準拠したモデル。
station_information と station_status を統合した Port モデルを提供。

公式ドキュメント:
- GBFS仕様: https://gbfs.org/documentation/reference/
- station_information: https://gbfs.org/specification/reference/#station_informationjson
- station_status: https://gbfs.org/specification/reference/#station_statusjson
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


# =============================================================================
# シェアサイクルポートモデル
# =============================================================================

class Port(BaseModel):
    """
    シェアサイクルポート
    
    GBFS の station_information と station_status を統合したモデル。
    ポートの静的情報（位置、名称）と動的情報（空き台数）を1つのモデルで表現。
    
    GBFS仕様参照:
    - station_information: ポートの静的情報
      https://gbfs.org/specification/reference/#station_informationjson
    - station_status: ポートのリアルタイム状態
      https://gbfs.org/specification/reference/#station_statusjson
    
    Attributes:
        id (str): ポートID（GBFS station_id）
        name (str): ポート名称（GBFS name）
        operator (str): 事業者識別子（"docomo" / "hellocycling"）
        coordinates (list[float]): 座標 [経度, 緯度]（GBFS lon, lat）
        bikes_available (int): 利用可能な自転車数（GBFS num_bikes_available）
        docks_available (int): 利用可能なドック数（GBFS num_docks_available）
        is_renting (bool): 貸出中かどうか（GBFS is_renting）
        is_returning (bool): 返却可能かどうか（GBFS is_returning）
        last_reported (datetime): 最終更新日時（GBFS last_reported）
    
    使用例:
        Port(
            id="docomo_kyoto_001",
            name="京都駅八条口ポート",
            operator="docomo",
            coordinates=[135.7590, 34.9855],
            bikes_available=5,
            docks_available=10,
            is_renting=True,
            is_returning=True,
            last_reported=datetime.now()
        )
    """
    id: str = Field(
        ...,
        description="ポートID（GBFS station_id）",
        examples=["docomo_kyoto_001", "hello_123"]
    )
    name: str = Field(
        ...,
        description="ポート名称",
        examples=["京都駅八条口ポート", "四条烏丸ステーション"]
    )
    operator: str = Field(
        ...,
        description="事業者識別子",
        examples=["docomo", "hellocycling"]
    )
    coordinates: list[float] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="座標 [経度, 緯度]",
        examples=[[135.7590, 34.9855]]
    )
    # GBFS station_status からの情報
    bikes_available: int = Field(
        ...,
        alias="bikesAvailable",
        ge=0,
        description="利用可能な自転車数（GBFS num_bikes_available）",
        examples=[5]
    )
    docks_available: int = Field(
        ...,
        alias="docksAvailable",
        ge=0,
        description="利用可能なドック数（GBFS num_docks_available）",
        examples=[10]
    )
    is_renting: bool = Field(
        ...,
        alias="isRenting",
        description="貸出可能かどうか（GBFS is_renting）"
    )
    is_returning: bool = Field(
        ...,
        alias="isReturning",
        description="返却可能かどうか（GBFS is_returning）"
    )
    last_reported: datetime = Field(
        ...,
        alias="lastReported",
        description="最終更新日時（GBFS last_reported、Unix timestamp から変換）"
    )
    
    class Config:
        populate_by_name = True


# =============================================================================
# ポートリストレスポンスモデル
# =============================================================================

class PortsData(BaseModel):
    """
    ポート一覧レスポンスデータ
    
    GET /api/ports のレスポンスに含まれるデータ。
    
    Attributes:
        ports (list[Port]): ポートリスト
        total_count (int): 総ポート数
        last_updated (datetime): データ最終更新日時
    
    設計根拠:
        - total_count: ページネーション実装時に使用
        - last_updated: クライアント側キャッシュ判断に使用
    """
    ports: list[Port] = Field(
        ...,
        description="ポートリスト"
    )
    total_count: int = Field(
        ...,
        alias="totalCount",
        ge=0,
        description="総ポート数"
    )
    last_updated: datetime = Field(
        ...,
        alias="lastUpdated",
        description="データ最終更新日時"
    )
    
    class Config:
        populate_by_name = True


# =============================================================================
# GBFS 生データモデル（内部使用）
# =============================================================================

class GBFSStationInfo(BaseModel):
    """
    GBFS station_information の1ステーション
    
    GBFS仕様: https://gbfs.org/specification/reference/#station_informationjson
    
    内部使用のみ。API レスポンスには Port モデルを使用。
    """
    station_id: str
    name: str
    lat: float
    lon: float
    capacity: Optional[int] = None


class GBFSStationStatus(BaseModel):
    """
    GBFS station_status の1ステーション
    
    GBFS仕様: https://gbfs.org/specification/reference/#station_statusjson
    
    内部使用のみ。API レスポンスには Port モデルを使用。
    """
    station_id: str
    num_bikes_available: int
    num_docks_available: int
    is_renting: bool = True
    is_returning: bool = True
    last_reported: int  # Unix timestamp