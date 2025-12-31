"""
app/services/route_calculator.py

ルート計算サービス

A*アルゴリズムとサブグラフ化による最適化されたルート探索を提供。
安全道（is_safe属性）を考慮した重み付けルーティング。

公式ドキュメント:
- NetworkX A*: https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.shortest_paths.astar.astar_path.html
- NetworkX subgraph_view: https://networkx.org/documentation/stable/reference/classes/generated/networkx.classes.graphviews.subgraph_view.html
"""
import math
from typing import Optional, Callable, Union
from dataclasses import dataclass
import networkx as nx

try:
    import osmnx as ox
    HAS_OSMNX = True
except ImportError:
    HAS_OSMNX = False

from app.models.parking import Parking
from app.models.port import Port


# =============================================================================
# データクラス
# =============================================================================

@dataclass
class RouteResult:
    """
    ルート計算結果
    
    Attributes:
        nodes: ルートを構成するノードIDリスト
        coordinates: 座標リスト [[経度, 緯度], ...]
        distance: 総距離（メートル）
        duration: 所要時間（秒）
        safety_score: 安全スコア（0-10）
        safe_distance: 安全道の距離（メートル）
        normal_distance: 通常道の距離（メートル）
    """
    nodes: list[int]
    coordinates: list[list[float]]
    distance: float
    duration: float
    safety_score: float
    safe_distance: float
    normal_distance: float


# =============================================================================
# 重み計算
# =============================================================================

class WeightCalculator:
    """
    エッジ重み計算クラス
    
    安全度パラメータ（1-10）に基づいて、エッジの重みを計算。
    
    係数:
        safe_factor = 1.0 - (safety * 0.03)  # 0.97 ~ 0.70
        normal_factor = 1.0 + (safety * 0.2)  # 1.2 ~ 3.0
    """
    
    @staticmethod
    def get_factors(safety: int) -> tuple[float, float]:
        """安全度に応じた係数を計算"""
        safe_factor = 1.0 - (safety * 0.03)
        normal_factor = 1.0 + (safety * 0.2)
        return safe_factor, normal_factor
    
    @staticmethod
    def calculate_weight(length: float, is_safe: bool, safety: int) -> float:
        """エッジの重みを計算"""
        safe_factor, normal_factor = WeightCalculator.get_factors(safety)
        return length * safe_factor if is_safe else length * normal_factor


# =============================================================================
# 地理計算ユーティリティ
# =============================================================================

def haversine_distance(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    2点間のHaversine距離（メートル）
    
    参照: https://pypi.org/project/haversine/
    """
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def create_heuristic(G: nx.MultiDiGraph, target_node: int) -> Callable:
    """
    A*用ヒューリスティック関数を生成
    
    参照: https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.shortest_paths.astar.astar_path.html
    """
    target_x = G.nodes[target_node]['x']
    target_y = G.nodes[target_node]['y']
    
    def heuristic(node: int, target: int) -> float:
        node_x = G.nodes[node]['x']
        node_y = G.nodes[node]['y']
        return haversine_distance(node_x, node_y, target_x, target_y)
    
    return heuristic


# =============================================================================
# サブグラフ処理
# =============================================================================

def calculate_bounding_box(
    origin: tuple[float, float],
    destination: tuple[float, float],
    margin_ratio: float = 0.2,
) -> dict:
    """バウンディングボックスを計算"""
    lon1, lat1 = origin
    lon2, lat2 = destination
    
    min_lon, max_lon = min(lon1, lon2), max(lon1, lon2)
    min_lat, max_lat = min(lat1, lat2), max(lat1, lat2)
    
    lon_margin = max((max_lon - min_lon) * margin_ratio, 0.005)
    lat_margin = max((max_lat - min_lat) * margin_ratio, 0.005)
    
    return {
        'min_lon': min_lon - lon_margin,
        'max_lon': max_lon + lon_margin,
        'min_lat': min_lat - lat_margin,
        'max_lat': max_lat + lat_margin,
    }


def create_subgraph_view(G: nx.MultiDiGraph, bbox: dict) -> nx.MultiDiGraph:
    """
    サブグラフビューを作成
    
    参照: https://networkx.org/documentation/stable/reference/classes/generated/networkx.classes.graphviews.subgraph_view.html
    """
    min_lon, max_lon = bbox['min_lon'], bbox['max_lon']
    min_lat, max_lat = bbox['min_lat'], bbox['max_lat']
    
    def filter_node(node: int) -> bool:
        x = G.nodes[node].get('x', 0)
        y = G.nodes[node].get('y', 0)
        return min_lon <= x <= max_lon and min_lat <= y <= max_lat
    
    return nx.subgraph_view(G, filter_node=filter_node)


# =============================================================================
# ルート計算サービス
# =============================================================================

class RouteCalculator:
    """
    ルート計算サービス
    
    最適化:
    1. A*アルゴリズム（Haversineヒューリスティック）
    2. サブグラフ化（バウンディングボックス内のみ探索）
    3. 事前計算（代表的なsafetyレベル）
    
    Attributes:
        graph: 道路グラフ
        parkings: 駐輪場リスト
        PRECOMPUTED_LEVELS: 事前計算するsafetyレベル
        BICYCLE_SPEED: 自転車速度（m/s）
        WALK_SPEED: 徒歩速度（m/s）
    """
    
    PRECOMPUTED_LEVELS = [1, 3, 5, 7, 10]
    BICYCLE_SPEED = 4.17  # 時速15km
    WALK_SPEED = 1.4      # 時速5km
    
    def __init__(self, graph: nx.MultiDiGraph, parkings: list[Parking] = None):
        """初期化"""
        self.graph = graph
        self.parkings = parkings or []
        self._precompute_edge_costs()
        
        print(f"RouteCalculator initialized:")
        print(f"  - Nodes: {len(graph.nodes):,}")
        print(f"  - Edges: {len(graph.edges):,}")
        print(f"  - Parkings: {len(self.parkings)}")
    
    def _precompute_edge_costs(self):
        """代表的なsafetyレベルの重みを事前計算"""
        print("Precomputing edge costs...")
        for safety in self.PRECOMPUTED_LEVELS:
            attr_name = f'cost_{safety}'
            safe_factor, normal_factor = WeightCalculator.get_factors(safety)
            
            for u, v, k, data in self.graph.edges(keys=True, data=True):
                length = data.get('length', 10)
                is_safe = data.get('is_safe', False)
                cost = length * safe_factor if is_safe else length * normal_factor
                self.graph[u][v][k][attr_name] = cost
        
        print(f"  -> Precomputed {len(self.PRECOMPUTED_LEVELS)} levels")
    
    def _get_weight(self, safety: int) -> Union[str, Callable]:
        """safetyに応じた重みを取得"""
        if safety in self.PRECOMPUTED_LEVELS:
            return f'cost_{safety}'
        
        safe_factor, normal_factor = WeightCalculator.get_factors(safety)
        
        def weight_func(u: int, v: int, data: dict) -> float:
            length = data.get('length', 10)
            is_safe = data.get('is_safe', False)
            return length * safe_factor if is_safe else length * normal_factor
        
        return weight_func
    
    def _find_nearest_node(self, lon: float, lat: float, graph: nx.MultiDiGraph = None) -> int:
        """座標から最寄りノードを検索"""
        G = graph if graph is not None else self.graph
        
        if HAS_OSMNX:
            return ox.nearest_nodes(G, lon, lat)
        
        min_dist = float('inf')
        nearest = None
        for node in G.nodes():
            node_x = G.nodes[node].get('x', 0)
            node_y = G.nodes[node].get('y', 0)
            dist = haversine_distance(lon, lat, node_x, node_y)
            if dist < min_dist:
                min_dist = dist
                nearest = node
        return nearest
    
    def _find_path_astar(
        self,
        graph: nx.MultiDiGraph,
        orig_node: int,
        dest_node: int,
        weight: Union[str, Callable],
    ) -> list[int]:
        """A*アルゴリズムでルート探索"""
        heuristic = create_heuristic(graph, dest_node)
        return nx.astar_path(
            graph,
            source=orig_node,
            target=dest_node,
            heuristic=heuristic,
            weight=weight,
        )
    
    def _find_route_with_subgraph(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        safety: int,
        margin_ratio: float = 0.2,
    ) -> list[int]:
        """サブグラフを使用してルート探索"""
        bbox = calculate_bounding_box(origin, destination, margin_ratio)
        subgraph = create_subgraph_view(self.graph, bbox)
        
        orig_node = self._find_nearest_node(origin[0], origin[1])
        dest_node = self._find_nearest_node(destination[0], destination[1])
        
        if orig_node not in subgraph or dest_node not in subgraph:
            bbox = calculate_bounding_box(origin, destination, margin_ratio=0.5)
            subgraph = create_subgraph_view(self.graph, bbox)
        
        weight = self._get_weight(safety)
        
        try:
            return self._find_path_astar(subgraph, orig_node, dest_node, weight)
        except nx.NetworkXNoPath:
            print("Subgraph search failed. Falling back to full graph.")
            return self._find_path_astar(self.graph, orig_node, dest_node, weight)
    
    def _calculate_route_info(self, route: list[int]) -> RouteResult:
        """ルートの詳細情報を計算"""
        coordinates = []
        total_distance = 0.0
        safe_distance = 0.0
        normal_distance = 0.0
        
        for node in route:
            x = self.graph.nodes[node]['x']
            y = self.graph.nodes[node]['y']
            coordinates.append([x, y])
        
        for u, v in zip(route[:-1], route[1:]):
            edge_data = self.graph.get_edge_data(u, v)
            if edge_data:
                min_length = float('inf')
                min_is_safe = False
                for key, data in edge_data.items():
                    length = data.get('length', 0)
                    if length < min_length:
                        min_length = length
                        min_is_safe = data.get('is_safe', False)
                
                total_distance += min_length
                if min_is_safe:
                    safe_distance += min_length
                else:
                    normal_distance += min_length
        
        safety_score = (safe_distance / total_distance * 10) if total_distance > 0 else 5.0
        duration = total_distance / self.BICYCLE_SPEED
        
        return RouteResult(
            nodes=route,
            coordinates=coordinates,
            distance=total_distance,
            duration=duration,
            safety_score=round(safety_score, 1),
            safe_distance=safe_distance,
            normal_distance=normal_distance,
        )
    
    # =========================================================================
    # 公開API
    # =========================================================================
    
    def calculate_direct_route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        safety: int,
    ) -> RouteResult:
        """
        直接ルート計算（UC-2）
        
        Args:
            origin: 出発地 (経度, 緯度)
            destination: 目的地 (経度, 緯度)
            safety: 安全度 (1-10)
        
        Returns:
            RouteResult
        """
        route = self._find_route_with_subgraph(origin, destination, safety)
        return self._calculate_route_info(route)
    
    def calculate_route_with_parking(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        safety: int,
    ) -> dict:
        """
        駐輪場経由ルート計算（UC-1）
        
        Returns:
            {parking, bicycle_route, walk_distance, walk_duration, total_distance, total_duration}
        """
        parking = self._find_nearest_parking(destination, max_distance=800)
        if parking is None:
            raise ValueError("目的地付近に駐輪場が見つかりません")
        
        parking_coords = (parking.coordinates[0], parking.coordinates[1])
        bicycle_route = self.calculate_direct_route(origin, parking_coords, safety)
        
        walk_distance = haversine_distance(
            parking_coords[0], parking_coords[1],
            destination[0], destination[1],
        )
        walk_duration = walk_distance / self.WALK_SPEED
        
        return {
            'parking': parking,
            'bicycle_route': bicycle_route,
            'walk_distance': walk_distance,
            'walk_duration': walk_duration,
            'total_distance': bicycle_route.distance + walk_distance,
            'total_duration': bicycle_route.duration + walk_duration,
        }
    
    def calculate_share_cycle_route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        safety: int,
        ports: list[Port],
    ) -> dict:
        """
        シェアサイクルルート計算（UC-3）
        
        Returns:
            {borrow_port, return_port, walk_to_port, bicycle_route, walk_from_port, total_distance, total_duration}
        """
        borrow_port, return_port = self._find_best_ports(origin, destination, ports)
        
        if borrow_port is None:
            raise ValueError("空きのあるポートが見つかりません")
        if return_port is None:
            raise ValueError("返却可能なポートが見つかりません")
        
        borrow_coords = (borrow_port.coordinates[0], borrow_port.coordinates[1])
        return_coords = (return_port.coordinates[0], return_port.coordinates[1])
        
        walk_to_port = haversine_distance(origin[0], origin[1], borrow_coords[0], borrow_coords[1])
        bicycle_route = self.calculate_direct_route(borrow_coords, return_coords, safety)
        walk_from_port = haversine_distance(return_coords[0], return_coords[1], destination[0], destination[1])
        
        walk_duration = (walk_to_port + walk_from_port) / self.WALK_SPEED
        
        return {
            'borrow_port': borrow_port,
            'return_port': return_port,
            'walk_to_port': walk_to_port,
            'bicycle_route': bicycle_route,
            'walk_from_port': walk_from_port,
            'total_distance': walk_to_port + bicycle_route.distance + walk_from_port,
            'total_duration': walk_duration + bicycle_route.duration,
        }
    
    # =========================================================================
    # ヘルパーメソッド
    # =========================================================================
    
    def _find_nearest_parking(self, location: tuple[float, float], max_distance: float = 500) -> Optional[Parking]:
        """最寄りの駐輪場を検索"""
        nearest = None
        min_dist = float('inf')
        for parking in self.parkings:
            dist = haversine_distance(location[0], location[1], parking.coordinates[0], parking.coordinates[1])
            if dist < min_dist and dist <= max_distance:
                min_dist = dist
                nearest = parking
        return nearest
    
    def _find_best_ports(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        ports: list[Port],
        min_bikes: int = 1,
        min_docks: int = 1,
    ) -> tuple[Optional[Port], Optional[Port]]:
        """最適な借りるポートと返すポートを検索"""
        borrow_port = None
        min_dist = float('inf')
        for port in ports:
            if port.bikes_available >= min_bikes:
                dist = haversine_distance(origin[0], origin[1], port.coordinates[0], port.coordinates[1])
                if dist < min_dist:
                    min_dist = dist
                    borrow_port = port
        
        return_port = None
        min_dist = float('inf')
        for port in ports:
            if port.docks_available >= min_docks:
                dist = haversine_distance(destination[0], destination[1], port.coordinates[0], port.coordinates[1])
                if dist < min_dist:
                    min_dist = dist
                    return_port = port
        
        return borrow_port, return_port