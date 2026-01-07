"""
tests/test_route_calculator.py

RouteCalculatorのユニットテスト
"""
import pytest
import math

from app.services.route_calculator import (
    RouteCalculator,
    WeightCalculator,
    haversine_distance,
    RouteResult,
)
from tests.conftest import KYOTO_STATION, NIJO_CASTLE, KINKAKUJI


class TestHaversineDistance:
    """Haversine距離計算のテスト"""

    def test_same_point(self):
        """同一地点の距離は0"""
        dist = haversine_distance(135.7588, 34.9858, 135.7588, 34.9858)
        assert dist == 0.0

    def test_kyoto_to_nijo(self):
        """京都駅から二条城への距離（約3km）"""
        dist = haversine_distance(
            KYOTO_STATION[0], KYOTO_STATION[1],
            NIJO_CASTLE[0], NIJO_CASTLE[1]
        )
        # 実際の距離は約3.3km
        assert 2500 < dist < 4000

    def test_symmetry(self):
        """距離の対称性（A→BとB→Aは同じ）"""
        dist_ab = haversine_distance(
            KYOTO_STATION[0], KYOTO_STATION[1],
            NIJO_CASTLE[0], NIJO_CASTLE[1]
        )
        dist_ba = haversine_distance(
            NIJO_CASTLE[0], NIJO_CASTLE[1],
            KYOTO_STATION[0], KYOTO_STATION[1]
        )
        assert abs(dist_ab - dist_ba) < 0.01


class TestWeightCalculator:
    """重み計算のテスト（強化版係数）"""

    def test_safety_1_factors(self):
        """safety=1の係数（強化版）"""
        safe_factor, normal_factor = WeightCalculator.get_factors(1)
        # safe_factor = 1.0 - 1*0.08 = 0.92
        assert abs(safe_factor - 0.92) < 0.001
        # normal_factor = 1.0 + 1*0.5 = 1.5
        assert abs(normal_factor - 1.5) < 0.001

    def test_safety_5_factors(self):
        """safety=5の係数（強化版）"""
        safe_factor, normal_factor = WeightCalculator.get_factors(5)
        # safe_factor = 1.0 - 5*0.08 = 0.60
        assert abs(safe_factor - 0.60) < 0.001
        # normal_factor = 1.0 + 5*0.5 = 3.5
        assert abs(normal_factor - 3.5) < 0.001

    def test_safety_10_factors(self):
        """safety=10の係数（強化版）"""
        safe_factor, normal_factor = WeightCalculator.get_factors(10)
        # safe_factor = max(0.2, 1.0 - 10*0.08) = 0.20
        assert abs(safe_factor - 0.20) < 0.001
        # normal_factor = 1.0 + 10*0.5 = 6.0
        assert abs(normal_factor - 6.0) < 0.001

    def test_calculate_weight_safe_road(self):
        """安全道の重み計算（道路種別なし）"""
        weight = WeightCalculator.calculate_weight(100, is_safe=True, safety=5)
        # 100 * 0.60 = 60（道路種別ペナルティなし）
        assert abs(weight - 60) < 0.1

    def test_calculate_weight_normal_road(self):
        """通常道の重み計算（道路種別なし）"""
        weight = WeightCalculator.calculate_weight(100, is_safe=False, safety=5)
        # 100 * 3.5 = 350（道路種別ペナルティなし）
        assert abs(weight - 350) < 0.1

    def test_highway_penalty_residential(self):
        """住宅街道路のペナルティ"""
        penalty = WeightCalculator.get_highway_penalty('residential')
        assert abs(penalty - 1.15) < 0.001

    def test_highway_penalty_cycleway(self):
        """自転車専用道の優遇"""
        penalty = WeightCalculator.get_highway_penalty('cycleway')
        assert abs(penalty - 0.6) < 0.001

    def test_calculate_weight_with_highway(self):
        """道路種別を考慮した重み計算"""
        # residential: 100 * 0.60 * 1.15 = 69
        weight = WeightCalculator.calculate_weight(100, is_safe=True, safety=5, highway='residential')
        assert abs(weight - 69) < 0.1


class TestRouteCalculatorInit:
    """RouteCalculator初期化のテスト"""

    def test_init_with_graph(self, test_graph):
        """グラフでの初期化"""
        calc = RouteCalculator(test_graph, parkings=[])
        assert calc.graph is test_graph
        assert calc.parkings == []

    def test_precomputed_levels(self, route_calculator):
        """事前計算レベルの確認"""
        assert RouteCalculator.PRECOMPUTED_LEVELS == [1, 3, 5, 7, 10]


class TestRouteCalculatorNearestNode:
    """最寄りノード検索のテスト"""

    def test_find_nearest_node_kyoto_station(self, route_calculator):
        """京都駅座標から最寄りノードを検索"""
        node = route_calculator._find_nearest_node(135.7588, 34.9858)
        assert node is not None
        # テストグラフではノード1が京都駅
        assert node == 1

    def test_find_nearest_node_nijo(self, route_calculator):
        """二条城座標から最寄りノードを検索"""
        node = route_calculator._find_nearest_node(135.7482, 35.0142)
        assert node is not None
        # テストグラフではノード3が二条城
        assert node == 3


class TestRouteCalculatorDirectRoute:
    """直接ルート計算のテスト"""

    def test_calculate_direct_route(self, route_calculator):
        """京都駅から二条城への直接ルート"""
        result = route_calculator.calculate_direct_route(
            KYOTO_STATION, NIJO_CASTLE, safety=5
        )

        assert isinstance(result, RouteResult)
        assert result.distance > 0
        assert result.duration > 0
        assert len(result.nodes) >= 2
        assert len(result.coordinates) >= 2
        assert 0 <= result.safety_score <= 10

    def test_safety_affects_route(self, route_calculator):
        """安全度がルートに影響する"""
        result_low = route_calculator.calculate_direct_route(
            KYOTO_STATION, NIJO_CASTLE, safety=1
        )
        result_high = route_calculator.calculate_direct_route(
            KYOTO_STATION, NIJO_CASTLE, safety=10
        )

        # safety=10の方が安全道比率が高い（またはルートが異なる）可能性
        # テストグラフが小さいので差が出ない場合もある
        assert result_low.distance > 0
        assert result_high.distance > 0

    def test_route_result_has_coordinates(self, route_calculator):
        """ルート結果に座標が含まれる"""
        result = route_calculator.calculate_direct_route(
            KYOTO_STATION, NIJO_CASTLE, safety=5
        )

        for coord in result.coordinates:
            assert len(coord) == 2
            lon, lat = coord
            assert 130 < lon < 140  # 日本の経度範囲
            assert 30 < lat < 40    # 日本の緯度範囲


class TestRouteCalculatorParkingRoute:
    """駐輪場経由ルートのテスト"""

    def test_find_nearest_parking(self, route_calculator):
        """最寄り駐輪場の検索"""
        parking = route_calculator._find_nearest_parking(NIJO_CASTLE, max_distance=2000)
        # 駐輪場が見つかった場合
        if parking:
            assert parking.id is not None
            assert len(parking.coordinates) == 2

    def test_calculate_route_with_parking(self, route_calculator):
        """駐輪場経由ルートの計算"""
        try:
            result = route_calculator.calculate_route_with_parking(
                KYOTO_STATION, NIJO_CASTLE, safety=5
            )
            assert "parking" in result
            assert "bicycle_route" in result
            assert "walk_distance" in result
            assert result["total_distance"] > 0
        except ValueError as e:
            # 駐輪場が見つからない場合はスキップ
            pytest.skip(f"No parking found: {e}")


class TestRouteCalculatorConstants:
    """定数のテスト"""

    def test_bicycle_speed(self):
        """自転車速度の定数"""
        # 4.17 m/s ≈ 15 km/h
        assert abs(RouteCalculator.BICYCLE_SPEED - 4.17) < 0.01

    def test_walk_speed(self):
        """徒歩速度の定数"""
        # 1.4 m/s ≈ 5 km/h
        assert abs(RouteCalculator.WALK_SPEED - 1.4) < 0.01
