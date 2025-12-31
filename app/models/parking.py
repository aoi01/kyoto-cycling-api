"""
app/models/parking.py

駐輪場関連のモデル定義

公式ドキュメント:
- Pydantic Models: https://docs.pydantic.dev/latest/concepts/models/
- Pydantic Fields: https://docs.pydantic.dev/latest/concepts/fields/
- Pydantic Aliases: https://docs.pydantic.dev/latest/concepts/alias/
"""
from pydantic import BaseModel, Field


class Parking(BaseModel):
    """
    駐輪場情報

    京都市オープンデータより取得した駐輪場情報。

    Attributes:
        id (str): 駐輪場ID（例: "parking_001"）
        name (str): 駐輪場名称
        coordinates (list[float]): 座標 [経度, 緯度]
        fee_description (str): 料金説明

    使用例:
        Parking(
            id="parking_001",
            name="京都市国際会館駅自転車等駐車場",
            coordinates=[135.785454, 35.063882],
            fee_description="月極 自転車月2800円"
        )
    """
    id: str = Field(
        ...,
        description="駐輪場ID",
        examples=["parking_001", "parking_123"]
    )
    name: str = Field(
        ...,
        description="駐輪場名称",
        examples=["京都市国際会館駅自転車等駐車場", "京都駅前駐輪場"]
    )
    coordinates: list[float] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="座標 [経度, 緯度]",
        examples=[[135.785454, 35.063882]]
    )
    fee_description: str = Field(
        default="料金情報なし",
        alias="feeDescription",
        description="料金説明",
        examples=["月極 自転車月2800円", "2時間まで100円 以降2時間毎50円"]
    )

    model_config = {"populate_by_name": True}


class ParkingsData(BaseModel):
    """
    駐輪場一覧レスポンスデータ

    GET /api/parkings のレスポンスに含まれるデータ。

    Attributes:
        parkings (list[Parking]): 駐輪場リスト
        total_count (int): 総件数
    """
    parkings: list[Parking] = Field(
        ...,
        description="駐輪場リスト"
    )
    total_count: int = Field(
        ...,
        alias="totalCount",
        ge=0,
        description="総件数",
        examples=[252]
    )

    model_config = {"populate_by_name": True}
