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
import numpy as np

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

    安全度パラメータ（1-5）に基づいて、エッジの重みを計算。
    is_safe=True の道のみを考慮し、現実的な迂回率を実現。

    設計方針:
    - 業界標準（GraphHopper, OSRM, OpenRouteService）を参考
    - 実際のサイクリストの行動（10-63%の迂回許容）に基づく
    - is_safeのみで判断（道路種別タグは無視）

    係数（改善版）:
        safe_factor = 1.0 - (safety * 0.08)   # safety=5で0.6（40%速く通れる）
        normal_factor = 1.0 + (safety * 0.2)  # safety=5で2.0（2倍遅く通れる）

    重み比率:
        safety=1: 1.3:1（約30%迂回）
        safety=3: 2.1:1（約110%迂回）- Google Maps風のバランス
        safety=5: 3.3:1（約230%迂回）
    """

    @staticmethod
    def get_factors(safety: int) -> tuple[float, float]:
        """
        安全度に応じた係数を計算

        Args:
            safety: 安全度（1-5）

        Returns:
            (safe_factor, normal_factor): 安全道係数、通常道係数
        """
        # 範囲外の値を1-5にクリップ（防御的プログラミング）
        safety = max(1, min(5, safety))

        # 安全道: safety=5で0.6（40%速く通れる扱い）
        safe_factor = max(0.6, 1.0 - (safety * 0.08))
        # 通常道: safety=5で2.0（2倍遅く通れる扱い）
        normal_factor = 1.0 + (safety * 0.2)
        return safe_factor, normal_factor

    @staticmethod
    def calculate_weight(length: float, is_safe: bool, safety: int) -> float:
        """
        エッジの重みを計算（is_safeのみ考慮）

        Args:
            length: エッジの長さ（メートル）
            is_safe: 安全道かどうか
            safety: 安全度（1-5）

        Returns:
            重み（コスト）
        """
        safe_factor, normal_factor = WeightCalculator.get_factors(safety)
        return length * (safe_factor if is_safe else normal_factor)


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
    
    PRECOMPUTED_LEVELS = [1, 3, 5]
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

                # is_safeのみに基づいてコストを計算
                cost = length * (safe_factor if is_safe else normal_factor)

                self.graph[u][v][k][attr_name] = cost

        print(f"  -> Precomputed {len(self.PRECOMPUTED_LEVELS)} levels")
    
    def _get_weight(self, safety: int) -> Union[str, Callable]:
        """
        safetyに応じた重みを取得

        Args:
            safety: 安全度（1-5）

        Returns:
            事前計算済みの場合は属性名、それ以外は重み計算関数
        """
        # 事前計算済みのレベル（1, 3, 5）の場合は属性名を返す
        if safety in self.PRECOMPUTED_LEVELS:
            return f'cost_{safety}'

        # それ以外は動的に計算する関数を返す
        safe_factor, normal_factor = WeightCalculator.get_factors(safety)

        def weight_func(u: int, v: int, data: dict) -> float:
            length = data.get('length', 10)
            is_safe = data.get('is_safe', False)
            # is_safeのみに基づいて重みを計算
            return length * (safe_factor if is_safe else normal_factor)

        return weight_func
    
    def _find_nearest_node(self, lon: float, lat: float, graph: nx.MultiDiGraph = None) -> int:
        """
        座標から最寄りノードを検索（NumPyベクトル化による高速化）

        Args:
            lon: 経度
            lat: 緯度
            graph: 検索対象グラフ（Noneの場合はself.graphを使用）

        Returns:
            最寄りノードのID
        """
        G = graph if graph is not None else self.graph

        # ノードIDと座標を配列に変換
        nodes = list(G.nodes())
        coords = np.array([[G.nodes[n].get('x', 0), G.nodes[n].get('y', 0)] for n in nodes])

        # ベクトル化されたHaversine距離計算
        target = np.array([lon, lat])

        # 緯度経度をラジアンに変換
        coords_rad = np.radians(coords)
        target_rad = np.radians(target)

        # Haversine公式（ベクトル化）
        dlat = coords_rad[:, 1] - target_rad[1]
        dlon = coords_rad[:, 0] - target_rad[0]

        a = (np.sin(dlat / 2) ** 2 +
             np.cos(target_rad[1]) * np.cos(coords_rad[:, 1]) * np.sin(dlon / 2) ** 2)
        distances = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

        # 最小距離のインデックスを取得
        nearest_idx = np.argmin(distances)
        return nodes[nearest_idx]
    
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
    
    def _find_route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        safety: int,
    ) -> list[int]:
        """A*アルゴリズムでルート探索（全グラフを対象）"""
        orig_node = self._find_nearest_node(origin[0], origin[1])
        dest_node = self._find_nearest_node(destination[0], destination[1])

        weight = self._get_weight(safety)

        return self._find_path_astar(self.graph, orig_node, dest_node, weight)

    def _find_walk_route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
    ) -> list[int]:
        """
        ダイクストラ法で徒歩ルート探索（距離最優先）

        安全度を考慮しない最短距離ルート。
        ダイクストラ法を使用して純粋に距離のみに基づいた最短経路を計算。

        Args:
            origin: 出発地 (経度, 緯度)
            destination: 目的地 (経度, 緯度)

        Returns:
            ノードIDのリスト
        """
        orig_node = self._find_nearest_node(origin[0], origin[1])
        dest_node = self._find_nearest_node(destination[0], destination[1])

        # ダイクストラ法で最短経路を探索（ヒューリスティックなし）
        try:
            return nx.shortest_path(
                self.graph,
                source=orig_node,
                target=dest_node,
                weight='length'
            )
        except nx.NetworkXNoPath:
            raise ValueError(f"No path found between origin and destination")
    
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

    def _calculate_walk_route_info(self, route: list[int]) -> dict:
        """
        徒歩ルートの詳細情報を計算

        Returns:
            {
                'coordinates': [[lon, lat], ...],
                'distance': 総距離（メートル）,
                'duration': 所要時間（秒）
            }
        """
        coordinates = []
        total_distance = 0.0

        for node in route:
            x = self.graph.nodes[node]['x']
            y = self.graph.nodes[node]['y']
            coordinates.append([x, y])

        for u, v in zip(route[:-1], route[1:]):
            edge_data = self.graph.get_edge_data(u, v)
            if edge_data:
                # 複数エッジがある場合は最短を選択
                min_length = float('inf')
                for key, data in edge_data.items():
                    length = data.get('length', 0)
                    if length < min_length:
                        min_length = length

                total_distance += min_length

        # 徒歩速度: 1.4 m/s (時速5km)
        duration = total_distance / self.WALK_SPEED

        return {
            'coordinates': coordinates,
            'distance': total_distance,
            'duration': duration,
        }
    
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

        A*アルゴリズムを使用して最適なルートを計算。
        ヒューリスティック（直線距離）により、目的地方向の探索を優先し、
        Dijkstra法と比べて大幅に計算量を削減。

        Args:
            origin: 出発地 (経度, 緯度)
            destination: 目的地 (経度, 緯度)
            safety: 安全度 (1-5)

        Returns:
            RouteResult
        """
        route = self._find_route(origin, destination, safety)
        return self._calculate_route_info(route)
    
    def calculate_route_with_parking(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        safety: int,
    ) -> dict:
        """
        駐輪場経由ルート計算（UC-1）

        自転車ルート（出発地→駐輪場）と徒歩ルート（駐輪場→目的地）を計算。

        Returns:
            {
                'parking': Parking,
                'bicycle_route': RouteResult,
                'walk_route': RouteResult,
                'walk_distance': 徒歩距離（メートル）,
                'walk_duration': 徒歩所要時間（秒）,
                'total_distance': 総距離（メートル）,
                'total_duration': 総所要時間（秒）
            }
        """
        # 距離制限なしで最寄りの駐輪場を検索
        parking = self._find_nearest_parking(destination)
        if parking is None:
            raise ValueError("駐輪場が見つかりません")

        parking_coords = (parking.coordinates[0], parking.coordinates[1])
        bicycle_route = self.calculate_direct_route(origin, parking_coords, safety)

        # 徒歩ルートはA*で探索（道路に沿ったルート）
        try:
            walk_route_nodes = self._find_walk_route(parking_coords, destination)
            walk_route_info = self._calculate_walk_route_info(walk_route_nodes)
        except Exception as e:
            # ルートが見つからない場合は直線距離にフォールバック
            print(f"Walk route not found: {e}. Using haversine distance as fallback.")
            walk_distance = haversine_distance(
                parking_coords[0], parking_coords[1],
                destination[0], destination[1],
            )
            walk_route_info = {
                'coordinates': [list(parking_coords), list(destination)],
                'distance': walk_distance,
                'duration': walk_distance / self.WALK_SPEED,
            }

        return {
            'parking': parking,
            'bicycle_route': bicycle_route,
            'walk_route': walk_route_info,
            'walk_distance': walk_route_info['distance'],
            'walk_duration': walk_route_info['duration'],
            'total_distance': bicycle_route.distance + walk_route_info['distance'],
            'total_duration': bicycle_route.duration + walk_route_info['duration'],
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

        出発地→レンタルポート（徒歩、A*で探索）
        レンタルポート→返却ポート（自転車）
        返却ポート→目的地（徒歩、A*で探索）

        Returns:
            {
                'borrow_port': Port,
                'return_port': Port,
                'walk_to_port_route': 徒歩ルート情報,
                'walk_to_port': 距離（メートル）,
                'bicycle_route': RouteResult,
                'walk_from_port_route': 徒歩ルート情報,
                'walk_from_port': 距離（メートル）,
                'total_distance': 総距離（メートル）,
                'total_duration': 総所要時間（秒）
            }
        """
        borrow_port, return_port = self._find_best_ports(origin, destination, ports)

        if borrow_port is None:
            raise ValueError("空きのあるポートが見つかりません")
        if return_port is None:
            raise ValueError("返却可能なポートが見つかりません")

        borrow_coords = (borrow_port.coordinates[0], borrow_port.coordinates[1])
        return_coords = (return_port.coordinates[0], return_port.coordinates[1])

        # 出発地→レンタルポートの徒歩ルート（A*探索）
        try:
            walk_to_port_nodes = self._find_walk_route(origin, borrow_coords)
            walk_to_port_info = self._calculate_walk_route_info(walk_to_port_nodes)
        except Exception as e:
            # ルートが見つからない場合は直線距離にフォールバック
            print(f"Walk route to port not found: {e}. Using haversine distance as fallback.")
            walk_distance = haversine_distance(origin[0], origin[1], borrow_coords[0], borrow_coords[1])
            walk_to_port_info = {
                'coordinates': [list(origin), list(borrow_coords)],
                'distance': walk_distance,
                'duration': walk_distance / self.WALK_SPEED,
            }

        # レンタルポート→返却ポートの自転車ルート
        bicycle_route = self.calculate_direct_route(borrow_coords, return_coords, safety)

        # 返却ポート→目的地の徒歩ルート（A*探索）
        try:
            walk_from_port_nodes = self._find_walk_route(return_coords, destination)
            walk_from_port_info = self._calculate_walk_route_info(walk_from_port_nodes)
        except Exception as e:
            # ルートが見つからない場合は直線距離にフォールバック
            print(f"Walk route from port not found: {e}. Using haversine distance as fallback.")
            walk_distance = haversine_distance(return_coords[0], return_coords[1], destination[0], destination[1])
            walk_from_port_info = {
                'coordinates': [list(return_coords), list(destination)],
                'distance': walk_distance,
                'duration': walk_distance / self.WALK_SPEED,
            }

        total_walk_distance = walk_to_port_info['distance'] + walk_from_port_info['distance']
        total_walk_duration = walk_to_port_info['duration'] + walk_from_port_info['duration']

        return {
            'borrow_port': borrow_port,
            'return_port': return_port,
            'walk_to_port_route': walk_to_port_info,
            'walk_to_port': walk_to_port_info['distance'],
            'bicycle_route': bicycle_route,
            'walk_from_port_route': walk_from_port_info,
            'walk_from_port': walk_from_port_info['distance'],
            'total_distance': total_walk_distance + bicycle_route.distance,
            'total_duration': total_walk_duration + bicycle_route.duration,
        }
    
    # =========================================================================
    # ヘルパーメソッド
    # =========================================================================
    
    def _find_nearest_parking(self, location: tuple[float, float], max_distance: float = None) -> Optional[Parking]:
        """
        最寄りの駐輪場を検索

        Args:
            location: 基準位置 (経度, 緯度)
            max_distance: 最大距離（メートル）。Noneの場合は距離制限なし

        Returns:
            最寄りの駐輪場、または見つからない場合はNone
        """
        if not self.parkings:
            return None

        nearest = None
        min_dist = float('inf')
        for parking in self.parkings:
            dist = haversine_distance(location[0], location[1], parking.coordinates[0], parking.coordinates[1])
            if dist < min_dist:
                # max_distanceが指定されている場合はチェック
                if max_distance is None or dist <= max_distance:
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
        """
        最適な借りるポートと返すポートを検索（同じ会社のものを選ぶ）

        borrowとreturnポートは同じoperatorのものを選択して、
        会社を統一したシェアサイクル利用体験を提供する。
        """
        # 1. 借りるポートを探す
        borrow_port = None
        min_dist = float('inf')
        for port in ports:
            if port.bikes_available >= min_bikes:
                dist = haversine_distance(origin[0], origin[1], port.coordinates[0], port.coordinates[1])
                if dist < min_dist:
                    min_dist = dist
                    borrow_port = port

        # borrowポートが見つからない場合は返却ポートも見つけられない
        if borrow_port is None:
            return None, None

        # 2. borrowポートと同じ会社の返すポートを探す
        return_port = None
        min_dist = float('inf')
        for port in ports:
            # 同じ会社で、返却可能なドックがあるポート
            if port.operator == borrow_port.operator and port.docks_available >= min_docks:
                dist = haversine_distance(destination[0], destination[1], port.coordinates[0], port.coordinates[1])
                if dist < min_dist:
                    min_dist = dist
                    return_port = port

        return borrow_port, return_port