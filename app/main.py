"""
app/main.py

京都自転車安全ルートナビ API - メインアプリケーション

起動コマンド:
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

環境変数:
  MAPBOX_ACCESS_TOKEN: Mapbox APIトークン
  GRAPH_PATH: グラフファイルパス (デフォルト: app/data/graph/kyoto_bike_graph.pkl)
"""
import os
import pickle
from contextlib import asynccontextmanager
from typing import Optional

# .envファイルを読み込む（os.getenvより前に実行）
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.services.route_calculator import RouteCalculator
from app.services.gbfs_client import GBFSClient
from app.models.parking import Parking
from app.routers.route import router as route_router
from app.routers.ports import router as ports_router
from app.data import PARKINGS


# =============================================================================
# 設定
# =============================================================================

class Settings:
    """アプリケーション設定"""
    MAPBOX_ACCESS_TOKEN: str = os.getenv("MAPBOX_ACCESS_TOKEN", "")
    GRAPH_PATH: str = os.getenv("GRAPH_PATH", "app/data/graph/kyoto_bike_graph.pkl")

    # CORS設定
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",      # Vite開発サーバー
        "http://localhost:3000",      # その他
        "https://your-frontend.com",  # 本番環境
    ]


settings = Settings()


# =============================================================================
# データローダー
# =============================================================================

def load_graph(path: str):
    """グラフデータを読み込む"""
    print(f"Loading graph from {path}...")

    try:
        with open(path, "rb") as f:
            graph = pickle.load(f)
        print(f"  -> Loaded: {len(graph.nodes):,} nodes, {len(graph.edges):,} edges")
        return graph
    except FileNotFoundError:
        print(f"  -> Graph file not found: {path}")
        print("  -> Creating minimal demo graph...")
        return _create_demo_graph()


def _create_demo_graph():
    """デモ用の最小グラフを作成"""
    import networkx as nx

    G = nx.MultiDiGraph()

    # 京都の主要スポット
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
        (1, 3, {'length': 3500, 'is_safe': False}),  # 直通（危険）
        (3, 1, {'length': 3500, 'is_safe': False}),
    ]
    G.add_edges_from(edges)

    return G


# =============================================================================
# Lifespan（起動・終了処理）
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    アプリケーションライフサイクル管理

    参照: https://fastapi.tiangolo.com/advanced/events/
    「lifespanパラメータを使用すると、startupとshutdownの
     ロジックを1つのコンテキストマネージャーで定義できる」

    Startup:
    1. グラフデータをロード
    2. 駐輪場データをロード
    3. RouteCalculator初期化（事前計算含む）
    4. GBFSClient初期化

    Shutdown:
    1. クライアントのクローズ
    2. リソース解放
    """
    # === Startup ===
    print("="*60)
    print("Starting Kyoto Bike Navi API...")
    print("="*60)

    # 1. グラフデータをロード
    graph = load_graph(settings.GRAPH_PATH)
    app.state.graph = graph

    # 2. 駐輪場データをロード（app/data/parkings.pyから）
    print(f"Loading parkings from app/data/parkings.py...")
    parkings = PARKINGS
    print(f"  -> Loaded: {len(parkings)} parkings")
    app.state.parkings = parkings

    # 3. RouteCalculator初期化
    print("Initializing RouteCalculator...")
    route_calculator = RouteCalculator(graph, parkings=parkings)
    app.state.route_calculator = route_calculator

    # 4. GBFSClient初期化
    print("Initializing GBFSClient...")
    gbfs_client = GBFSClient()
    await gbfs_client.initialize()
    app.state.gbfs_client = gbfs_client

    print("="*60)
    print("API Ready!")
    print("="*60)

    yield  # アプリケーション実行中

    # === Shutdown ===
    print("Shutting down...")

    # クライアントのクローズ
    await gbfs_client.close()

    print("Shutdown complete.")


# =============================================================================
# FastAPIアプリケーション
# =============================================================================

app = FastAPI(
    title="京都自転車安全ルートナビ API",
    description="""
京都を自転車で安全に観光するためのルート案内API

## 機能
- 安全道を考慮したルート検索
- 駐輪場経由ルート
- シェアサイクル対応（GBFS）
- 音声ナビ指示

## 安全度パラメータ
- `safety=1`: 最短距離重視
- `safety=5`: バランス
- `safety=10`: 安全最優先
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ルーター登録
app.include_router(route_router)
app.include_router(ports_router)


# =============================================================================
# ヘルスチェック・デバッグエンドポイント
# =============================================================================

@app.get("/health", tags=["system"])
async def health_check():
    """ヘルスチェック（Cloud Run用）"""
    return {"status": "healthy"}


@app.get("/debug/config", tags=["debug"])
async def get_config():
    """設定確認（デバッグ用）"""
    token = settings.MAPBOX_ACCESS_TOKEN
    return {
        "mapbox_token_set": bool(token),
        "mapbox_token_prefix": token[:20] + "..." if len(token) > 20 else "(empty)",
        "graph_path": settings.GRAPH_PATH,
    }


@app.get("/debug/graph-info", tags=["debug"])
async def get_graph_info():
    """グラフ情報を取得（デバッグ用）"""
    graph = app.state.graph

    # サンプルエッジの属性を取得
    sample_edge = None
    for u, v, k, data in graph.edges(keys=True, data=True):
        sample_edge = data
        break

    return {
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "sample_edge_attributes": list(sample_edge.keys()) if sample_edge else [],
        "precomputed_levels": RouteCalculator.PRECOMPUTED_LEVELS
    }


@app.get("/debug/test-route", tags=["debug"])
async def test_route(
    safety: int = 5
):
    """
    テストルート計算（京都駅 → 二条城）

    Args:
        safety: 安全度 1-10
    """
    route_calculator: RouteCalculator = app.state.route_calculator

    origin = (135.7588, 34.9858)      # 京都駅
    destination = (135.7482, 35.0142)  # 二条城

    try:
        result = route_calculator.calculate_direct_route(origin, destination, safety)

        return {
            "success": True,
            "origin": "京都駅",
            "destination": "二条城",
            "safety": safety,
            "result": {
                "distance": f"{result.distance:.0f}m",
                "duration": f"{result.duration:.0f}s ({result.duration/60:.1f}min)",
                "safety_score": result.safety_score,
                "safe_road_ratio": f"{result.safe_distance/result.distance*100:.1f}%",
                "nodes_count": len(result.nodes)
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/debug/weight-factors", tags=["debug"])
async def get_weight_factors():
    """
    安全度ごとの重み係数を表示

    設計確認用:
    - safe_factor: 安全道の係数（1未満で優遇）
    - normal_factor: 通常道の係数（1以上でペナルティ）
    """
    from app.services.route_calculator import WeightCalculator

    factors = {}
    for safety in range(1, 11):
        safe_factor, normal_factor = WeightCalculator.get_factors(safety)
        factors[f"safety_{safety}"] = {
            "safe_factor": round(safe_factor, 3),
            "normal_factor": round(normal_factor, 3),
            "safe_100m_cost": round(100 * safe_factor, 1),
            "normal_100m_cost": round(100 * normal_factor, 1)
        }

    return {
        "description": "100mの道路に対するコスト（重み）",
        "factors": factors
    }


# =============================================================================
# メイン（直接実行時）
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
