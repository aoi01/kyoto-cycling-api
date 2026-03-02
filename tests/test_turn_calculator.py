"""
tests/test_turn_calculator.py

ターン計算ユーティリティのユニットテスト
"""
import pytest
import math

from app.services.turn_calculator import (
    calculate_bearing,
    calculate_turn_angle,
    classify_turn,
    classify_turn_with_direction,
    get_turn_cost,
    calculate_turn_cost_from_bearings,
    TURN_COSTS,
    TURN_THRESHOLDS,
)


class TestCalculateBearing:
    """方位角計算のテスト"""

    def test_bearing_north(self):
        """北への方位角は0度（または360度）"""
        # 同じ経度で緯度が増える = 北へ移動
        bearing = calculate_bearing(135.0, 35.0, 135.0, 35.01)
        # 北は0度または360度（許容範囲で判定）
        assert bearing < 1.0 or bearing > 359.0

    def test_bearing_east(self):
        """東への方位角は90度"""
        # 同じ緯度で経度が増える = 東へ移動
        bearing = calculate_bearing(135.0, 35.0, 135.01, 35.0)
        assert 89.0 < bearing < 91.0

    def test_bearing_south(self):
        """南への方位角は180度"""
        # 同じ経度で緯度が減る = 南へ移動
        bearing = calculate_bearing(135.0, 35.0, 135.0, 34.99)
        assert 179.0 < bearing < 181.0

    def test_bearing_west(self):
        """西への方位角は270度"""
        # 同じ緯度で経度が減る = 西へ移動
        bearing = calculate_bearing(135.0, 35.0, 134.99, 35.0)
        assert 269.0 < bearing < 271.0

    def test_bearing_symmetry(self):
        """逆方向の方位角は約180度異なる"""
        bearing_there = calculate_bearing(135.0, 35.0, 135.01, 35.01)
        bearing_back = calculate_bearing(135.01, 35.01, 135.0, 35.0)
        diff = abs(bearing_there - bearing_back)
        # 180度の差（または180度に近い）
        assert abs(diff - 180) < 1.0 or abs(diff - 180) > 179.0


class TestCalculateTurnAngle:
    """ターン角度計算のテスト"""

    def test_straight_ahead(self):
        """直進（同じ方向）は0度"""
        angle = calculate_turn_angle(0, 10)  # ほぼ同じ方向
        assert angle < TURN_THRESHOLDS['straight']

    def test_right_angle_turn(self):
        """直角右折は90度"""
        angle = calculate_turn_angle(0, 90)  # 北から東へ
        assert 89.0 < angle < 91.0

    def test_left_angle_turn(self):
        """直角左折も90度（絶対値）"""
        angle = calculate_turn_angle(0, 270)  # 北から西へ
        assert 89.0 < angle < 91.0

    def test_uturn(self):
        """Uターンは180度"""
        angle = calculate_turn_angle(0, 180)  # 北から南へ
        assert 179.0 < angle <= 180.0

    def test_slight_right(self):
        """緩やかな右カーブ"""
        angle = calculate_turn_angle(0, 30)  # 北から北東へ
        assert TURN_THRESHOLDS['straight'] < angle < TURN_THRESHOLDS['slight']


class TestClassifyTurn:
    """ターン分類のテスト"""

    def test_classify_straight(self):
        """直進の分類"""
        turn_type = classify_turn(5)  # 5度は直進
        assert turn_type == 'straight'

    def test_classify_slight(self):
        """緩やかなカーブの分類"""
        turn_type = classify_turn(30)  # 30度は緩やか
        assert turn_type == 'slight'

    def test_classify_normal(self):
        """通常のカーブの分類"""
        turn_type = classify_turn(90)  # 90度は通常
        assert turn_type == 'normal'

    def test_classify_sharp(self):
        """急カーブの分類"""
        turn_type = classify_turn(150)  # 150度は急
        assert turn_type == 'sharp'


class TestClassifyTurnWithDirection:
    """方向を考慮したターン分類のテスト"""

    def test_right_turn(self):
        """右折の分類"""
        # 北(0°)から東(90°)へ = 右折
        turn_type = classify_turn_with_direction(90, 0, 90)
        assert turn_type == 'right'

    def test_left_turn(self):
        """左折の分類"""
        # 北(0°)から西(270°)へ = 左折
        turn_type = classify_turn_with_direction(90, 0, 270)
        assert turn_type == 'left'

    def test_slight_right(self):
        """緩やかな右カーブ"""
        turn_type = classify_turn_with_direction(30, 0, 30)
        assert turn_type == 'slight_right'

    def test_slight_left(self):
        """緩やかな左カーブ"""
        turn_type = classify_turn_with_direction(30, 0, 330)
        assert turn_type == 'slight_left'

    def test_uturn(self):
        """Uターンの分類"""
        turn_type = classify_turn_with_direction(180, 0, 180)
        assert turn_type == 'uturn'

    def test_straight_not_turn(self):
        """直進はターンではない"""
        turn_type = classify_turn_with_direction(10, 0, 10)
        assert turn_type == 'straight'


class TestGetTurnCost:
    """ターンコスト取得のテスト"""

    def test_straight_cost_zero(self):
        """直進はコスト0"""
        cost = get_turn_cost('straight')
        assert cost == 0

    def test_right_turn_more_expensive_than_left(self):
        """右折は左折より高コスト（日本の道路事情）"""
        right_cost = get_turn_cost('right')
        left_cost = get_turn_cost('left')
        assert right_cost > left_cost

    def test_uturn_most_expensive(self):
        """Uターンは最も高コスト"""
        uturn_cost = get_turn_cost('uturn')
        for turn_type, cost in TURN_COSTS.items():
            if turn_type != 'uturn':
                assert uturn_cost > cost

    def test_all_costs_defined(self):
        """全ターンタイプのコストが定義されている"""
        expected_types = [
            'straight', 'slight_left', 'left', 'sharp_left',
            'slight_right', 'right', 'sharp_right', 'uturn'
        ]
        for turn_type in expected_types:
            assert turn_type in TURN_COSTS


class TestCalculateTurnCostFromBearings:
    """方位角からの直接コスト計算テスト"""

    def test_straight_cost_from_bearings(self):
        """直進時のコストは0"""
        cost = calculate_turn_cost_from_bearings(0, 10)  # ほぼ直進
        assert cost == 0

    def test_right_turn_cost_from_bearings(self):
        """右折のコストは50m相当"""
        cost = calculate_turn_cost_from_bearings(0, 90)  # 北から東へ
        assert cost == TURN_COSTS['right']

    def test_left_turn_cost_from_bearings(self):
        """左折のコストは25m相当"""
        cost = calculate_turn_cost_from_bearings(0, 270)  # 北から西へ
        assert cost == TURN_COSTS['left']


class TestTurnCostValues:
    """ターンコストの値の妥当性テスト"""

    def test_cost_hierarchy(self):
        """コストの階層構造（日本の自転車事情に合わせて）"""
        # 直進 < 緩やか左 < 左 < 急左 < 緩やか右 < 右 < 急右 < Uターン
        costs = TURN_COSTS

        # 左折系の階層
        assert costs['slight_left'] < costs['left'] < costs['sharp_left']

        # 右折系の階層
        assert costs['slight_right'] < costs['right'] < costs['sharp_right']

        # 右折は左折より高い（日本では右折が危険）
        assert costs['slight_right'] > costs['slight_left']
        assert costs['right'] > costs['left']

        # Uターンは最も高い
        assert costs['uturn'] > costs['sharp_right']
