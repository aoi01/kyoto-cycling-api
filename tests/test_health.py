"""
tests/test_health.py

ヘルスチェックとデバッグエンドポイントのテスト
"""
import pytest


class TestHealthCheck:
    """ヘルスチェックエンドポイントのテスト"""

    async def test_health_returns_healthy(self, async_client):
        """GET /health が healthy を返す"""
        response = await async_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestDebugEndpoints:
    """デバッグエンドポイントのテスト"""

    async def test_graph_info(self, async_client):
        """GET /debug/graph-info がグラフ情報を返す"""
        response = await async_client.get("/debug/graph-info")

        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert data["nodes"] > 0
        assert data["edges"] > 0

    async def test_weight_factors(self, async_client):
        """GET /debug/weight-factors が係数情報を返す"""
        response = await async_client.get("/debug/weight-factors")

        assert response.status_code == 200
        data = response.json()
        assert "factors" in data
        assert "description" in data

        # safety_1 から safety_10 まで存在することを確認
        for i in range(1, 11):
            key = f"safety_{i}"
            assert key in data["factors"]
            factor = data["factors"][key]
            assert "safe_factor" in factor
            assert "normal_factor" in factor

    async def test_test_route(self, async_client):
        """GET /debug/test-route がルートを計算する"""
        response = await async_client.get("/debug/test-route", params={"safety": 5})

        assert response.status_code == 200
        data = response.json()
        assert "success" in data

        # テストグラフでも計算できる場合
        if data["success"]:
            assert "result" in data
            assert "distance" in data["result"]
            assert "duration" in data["result"]
