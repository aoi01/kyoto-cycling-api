"""
tests/test_route_api.py

ルート検索API（GET /api/route）のテスト
"""
import pytest

from tests.conftest import KYOTO_STATION, NIJO_CASTLE, KINKAKUJI, TOKYO_STATION


class TestRouteAPIValidation:
    """バリデーションエラーのテスト"""

    async def test_missing_origin(self, async_client):
        """originパラメータが不足している場合"""
        response = await async_client.get(
            "/api/route",
            params={
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "my-cycle",
                "safety": 5,
            }
        )
        # FastAPIは必須パラメータ不足で422を返す
        assert response.status_code == 422

    async def test_missing_destination(self, async_client):
        """destinationパラメータが不足している場合"""
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "mode": "my-cycle",
                "safety": 5,
            }
        )
        assert response.status_code == 422

    async def test_invalid_origin_format(self, async_client):
        """originの形式が不正な場合"""
        response = await async_client.get(
            "/api/route",
            params={
                "origin": "invalid",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "my-cycle",
                "safety": 5,
            }
        )
        # パターンマッチの失敗で422または200でエラーレスポンス
        assert response.status_code in [200, 422]
        if response.status_code == 200:
            data = response.json()
            assert data.get("success") is False

    async def test_safety_below_range(self, async_client):
        """safetyが範囲外（0）の場合"""
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "my-cycle",
                "safety": 0,
            }
        )
        assert response.status_code == 422

    async def test_safety_above_range(self, async_client):
        """safetyが範囲外（6）の場合"""
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "my-cycle",
                "safety": 6,
            }
        )
        assert response.status_code == 422

    async def test_invalid_mode(self, async_client):
        """modeが不正な場合"""
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "invalid-mode",
                "safety": 5,
            }
        )
        assert response.status_code == 422


class TestDirectRoute:
    """UC-2: 直接ルート（自転車）のテスト"""

    async def test_direct_route_basic(self, async_client):
        """基本的な直接ルート検索"""
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "my-cycle",
                "safety": 5,
                "needParking": "false",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert "segments" in data["data"]
        assert len(data["data"]["segments"]) >= 1

    async def test_direct_route_safety_min(self, async_client):
        """safety=1（最短距離重視）でのルート検索"""
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "my-cycle",
                "safety": 1,
                "needParking": "false",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_direct_route_safety_max(self, async_client):
        """safety=10（安全最優先）でのルート検索"""
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "my-cycle",
                "safety": 10,
                "needParking": "false",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestParkingRoute:
    """UC-1: 駐輪場経由ルートのテスト"""

    async def test_parking_route(self, async_client):
        """駐輪場経由のルート検索"""
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "my-cycle",
                "safety": 5,
                "needParking": "true",
            }
        )

        assert response.status_code == 200
        data = response.json()

        # 成功した場合は2つのセグメント（自転車 + 徒歩）
        if data["success"]:
            assert "data" in data
            # 駐輪場情報を含む可能性
            assert "segments" in data["data"]


class TestShareCycleRoute:
    """UC-3: シェアサイクルルートのテスト"""

    async def test_share_cycle_route_docomo(self, async_client):
        """docomoシェアサイクルでのルート検索"""
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "share-cycle",
                "safety": 5,
                "operators": "docomo",
            }
        )

        assert response.status_code == 200
        data = response.json()

        # シェアサイクルルートが計算された場合
        if data["success"]:
            assert "data" in data
            assert "segments" in data["data"]

    async def test_share_cycle_route_multiple_operators(self, async_client):
        """複数事業者でのルート検索"""
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "share-cycle",
                "safety": 5,
                "operators": "docomo,hellocycling",
            }
        )

        assert response.status_code == 200
        data = response.json()
        # レスポンスの形式が正しいことを確認
        assert "success" in data


class TestRouteAPIWithRealGraph:
    """実際のグラフデータを使用したテスト（統合テスト）"""

    async def test_real_graph_direct_route(self, async_client_real_graph):
        """実グラフでの直接ルート計算"""
        response = await async_client_real_graph.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "my-cycle",
                "safety": 5,
                "needParking": "false",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # 実際の距離とsafety_scoreを検証
        if "data" in data and "summary" in data["data"]:
            summary = data["data"]["summary"]
            assert summary["totalDistance"] > 0
            assert 0 <= summary.get("safetyScore", 5) <= 10
