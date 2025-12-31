"""
tests/conftest.py

pytest共通フィクスチャ

参照:
- pytest fixtures: https://docs.pytest.org/en/stable/fixture.html
- httpx TestClient: https://www.python-httpx.org/advanced/testing/
- FastAPI Testing: https://fastapi.tiangolo.com/tutorial/testing/
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
import networkx as nx

from httpx import AsyncClient, ASGITransport

from app.main import app, load_graph
from app.services.route_calculator import RouteCalculator
from app.services.gbfs_client import GBFSClient
from app.services.mapbox_client import MapboxClient
from app.models.port import Port, PortsData
from app.data import PARKINGS


# =============================================================================
# テスト用グラフ（軽量版）
# =============================================================================

@pytest.fixture
def test_graph():
    """テスト用の軽量グラフを作成"""
    G = nx.MultiDiGraph()

    # 京都の主要スポット（テスト用）
    nodes = [
        (1, {'x': 135.7588, 'y': 34.9858, 'name': '京都駅'}),
        (2, {'x': 135.7593, 'y': 35.0038, 'name': '四条烏丸'}),
        (3, {'x': 135.7482, 'y': 35.0142, 'name': '二条城'}),
        (4, {'x': 135.7292, 'y': 35.0394, 'name': '金閣寺'}),
        (5, {'x': 135.7850, 'y': 34.9949, 'name': '清水寺'}),
    ]
    G.add_nodes_from(nodes)

    # エッジ（双方向）
    edges = [
        (1, 2, {'length': 2000, 'is_safe': True}),
        (2, 1, {'length': 2000, 'is_safe': True}),
        (2, 3, {'length': 1800, 'is_safe': False}),
        (3, 2, {'length': 1800, 'is_safe': False}),
        (3, 4, {'length': 3000, 'is_safe': True}),
        (4, 3, {'length': 3000, 'is_safe': True}),
        (1, 5, {'length': 2500, 'is_safe': False}),
        (5, 1, {'length': 2500, 'is_safe': False}),
        (2, 5, {'length': 2200, 'is_safe': True}),
        (5, 2, {'length': 2200, 'is_safe': True}),
        (1, 3, {'length': 3500, 'is_safe': False}),
        (3, 1, {'length': 3500, 'is_safe': False}),
    ]
    G.add_edges_from(edges)

    return G


# =============================================================================
# RouteCalculatorフィクスチャ
# =============================================================================

@pytest.fixture
def route_calculator(test_graph):
    """テスト用RouteCalculator"""
    return RouteCalculator(test_graph, parkings=PARKINGS)


# =============================================================================
# モッククライアント
# =============================================================================

@pytest.fixture
def mock_gbfs_client():
    """GBFSClientのモック"""
    client = AsyncMock(spec=GBFSClient)

    # get_portsのモック戻り値
    now = datetime.now()
    mock_ports = [
        Port(
            id="port_1",
            name="テストポート1",
            coordinates=[135.7588, 34.9858],
            operator="docomo",
            bikes_available=5,
            docks_available=10,
            is_renting=True,
            is_returning=True,
            last_reported=now,
        ),
        Port(
            id="port_2",
            name="テストポート2",
            coordinates=[135.7482, 35.0142],
            operator="docomo",
            bikes_available=3,
            docks_available=7,
            is_renting=True,
            is_returning=True,
            last_reported=now,
        ),
    ]

    client.get_ports.return_value = PortsData(
        ports=mock_ports,
        total_count=len(mock_ports),
        last_updated=now,
    )
    client.initialize.return_value = None
    client.close.return_value = None

    return client


@pytest.fixture
def mock_mapbox_client():
    """MapboxClientのモック"""
    client = AsyncMock()

    # map_matchのモック戻り値
    client.map_match.return_value = {
        "code": "Ok",
        "matchings": [{
            "legs": [{
                "steps": []
            }],
            "geometry": {
                "coordinates": [[135.7588, 34.9858], [135.7482, 35.0142]]
            }
        }]
    }
    client.close.return_value = None

    return client


# =============================================================================
# FastAPIテストクライアント
# =============================================================================

@pytest.fixture
async def async_client(test_graph, mock_gbfs_client, mock_mapbox_client):
    """
    非同期HTTPテストクライアント

    app.stateに必要なオブジェクトを注入してテスト実行。
    """
    # app.stateに必要なオブジェクトを設定
    app.state.graph = test_graph
    app.state.parkings = PARKINGS
    app.state.route_calculator = RouteCalculator(test_graph, parkings=PARKINGS)
    app.state.gbfs_client = mock_gbfs_client
    app.state.mapbox_client = mock_mapbox_client

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def async_client_real_graph(mock_gbfs_client, mock_mapbox_client):
    """
    実際のグラフデータを使用するテストクライアント

    統合テスト用。グラフファイルが存在する場合のみ使用可能。
    """
    import os
    graph_path = "app/data/graph/kyoto_bike_graph.pkl"

    if not os.path.exists(graph_path):
        pytest.skip(f"Graph file not found: {graph_path}")

    try:
        graph = load_graph(graph_path)
    except ModuleNotFoundError as e:
        pytest.skip(f"Missing dependency for real graph: {e}")

    app.state.graph = graph
    app.state.parkings = PARKINGS
    app.state.route_calculator = RouteCalculator(graph, parkings=PARKINGS)
    app.state.gbfs_client = mock_gbfs_client
    app.state.mapbox_client = mock_mapbox_client

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# =============================================================================
# テスト用定数
# =============================================================================

# 京都市内の座標（テスト用）
KYOTO_STATION = (135.7588, 34.9858)
NIJO_CASTLE = (135.7482, 35.0142)
KINKAKUJI = (135.7292, 35.0394)
KIYOMIZU = (135.7850, 34.9949)

# 京都市外の座標（エラーテスト用）
TOKYO_STATION = (139.7671, 35.6812)
