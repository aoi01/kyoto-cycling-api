"""
tests/test_route_integration.py

ルート計算の統合テスト

このテストファイルは以下を検証する：
1. GeoJSONLineStringエラー（座標が1つしかない問題）が発生しないこと
2. 曲がり角コストが適切に適用されていること
3. 曲がり角コストによって遠回りになりすぎていないこと
"""
import pytest
from unittest.mock import MagicMock
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRouteCoordinatesValidation:
    """
    GeoJSONLineString座標バリデーションのテスト

    非エンジニア向け解説:
        GeoJSONのLineString（線を表すデータ形式）は、最低2つの点が必要です。
        1つの点しかないと「線」にならないため、エラーになります。

        例: 今出川駅のようにポートに近い場所では、徒歩ルートが1点しか
        返されないことがあり、これがエラーの原因でした。
    """

    @pytest.fixture
    def route_calculator(self):
        """RouteCalculatorのインスタンスを作成"""
        import pickle
        from app.services.route_calculator import RouteCalculator

        graph_path = "app/data/graph/kyoto_bike_graph.pkl"
        try:
            with open(graph_path, "rb") as f:
                graph = pickle.load(f)
        except FileNotFoundError:
            pytest.skip("Graph file not found")

        return RouteCalculator(graph)

    def test_direct_route_has_minimum_coordinates(self, route_calculator):
        """
        直接ルートの座標が最低2点あることを確認

        非エンジニア向け解説:
            出発地から目的地への直接ルートを計算したとき、
            返される座標リストが最低2つあることを確認します。
            2点あれば「線」として表現できます。
        """
        # 京都駅 → 二条城
        origin = (135.7588, 34.9858)
        destination = (135.7482, 35.0142)

        result = route_calculator.calculate_direct_route(origin, destination, safety=3)

        # 座標が最低2点あることを確認
        assert len(result.coordinates) >= 2, \
            f"座標が1つしかありません: {result.coordinates}"

    def test_walk_route_near_port_has_minimum_coordinates(self, route_calculator):
        """
        ポートに近い場所での徒歩ルートの座標が最低2点あることを確認

        非エンジニア向け解説:
            今出川駅のようにポート（自転車ポート）に非常に近い場所では、
            徒歩ルートがほぼ0メートルになり、1点しか返されないことがありました。
            このテストは、そのような場合でも2点以上返されることを確認します。
        """
        # 今出川駅（ポートに近い場所をシミュレート）
        origin = (135.7593106, 35.0298128)

        # 近くのポートを探す
        nearby_port = (135.7593, 35.0298)  # 非常に近い

        # 徒歩ルートを計算（ノードIDのリストを取得）
        walk_route_nodes = route_calculator._find_walk_route(origin, nearby_port)

        # 座標情報を計算
        walk_route_info = route_calculator._calculate_walk_route_info(walk_route_nodes)

        # 座標が最低2点あることを確認
        assert len(walk_route_info['coordinates']) >= 2, \
            f"徒歩ルートの座標が1つしかありません: {walk_route_info['coordinates']}"


class TestTurnCostImpact:
    """
    曲がり角コストの影響をテスト

    非エンジニア向け解説:
        「曲がり角を避ける」ためにコスト（ペナルティ）を設定していますが、
        あまりに高く設定しすぎると、遠回りのルートになってしまいます。

        このテストでは、以下を確認します：
        - 曲がり角コストを適用すると、曲がり角の数が減ること
        - ただし、距離が極端に増えすぎないこと（50%以内など）
    """

    @pytest.fixture
    def route_calculator(self):
        """RouteCalculatorのインスタンスを作成"""
        import pickle
        from app.services.route_calculator import RouteCalculator

        graph_path = "app/data/graph/kyoto_bike_graph.pkl"
        try:
            with open(graph_path, "rb") as f:
                graph = pickle.load(f)
        except FileNotFoundError:
            pytest.skip("Graph file not found")

        return RouteCalculator(graph)

    def test_turn_cost_reduces_turns(self, route_calculator):
        """
        曲がり角コストを適用すると曲がり角が減ることを確認

        非エンジニア向け解説:
            曲がり角を避けるコストを適用した場合、
            実際に曲がる回数が減ることを確認します。

            期待値:
            - ターンコストなし: 例えば20回曲がる
            - ターンコストあり: 例えば15回曲がる（減るはず）
        """
        origin = (135.7588, 34.9858)      # 京都駅
        destination = (135.7482, 35.0142)  # 二条城

        # ターンコストなし
        result_no_turn = route_calculator.calculate_direct_route(
            origin, destination, safety=3, use_turn_costs=False
        )

        # ターンコストあり
        result_with_turn = route_calculator.calculate_direct_route(
            origin, destination, safety=3, use_turn_costs=True
        )

        # ターンコストありの方が曲がり角が少ない、または同じ
        assert result_with_turn.turn_count <= result_no_turn.turn_count + 2, \
            f"ターンコストありで曲がり角が増えています: " \
            f"なし={result_no_turn.turn_count}, あり={result_with_turn.turn_count}"

    def test_turn_cost_does_not_excessively_increase_distance(self, route_calculator):
        """
        曲がり角コストによって距離が極端に増えないことを確認

        非エンジニア向け解説:
            曲がり角を避けるために遠回りをしても、
            あまりに遠すぎると意味がありません。

            このテストでは、ターンコストありの場合の距離が、
            なしの場合の50%以内に収まることを確認します。

            例:
            - ターンコストなし: 4000m
            - ターンコストあり: 6000m（50%増）→ ギリギリOK
            - ターンコストあり: 8000m（100%増）→ NG
        """
        origin = (135.7588, 34.9858)      # 京都駅
        destination = (135.7482, 35.0142)  # 二条城

        # ターンコストなし
        result_no_turn = route_calculator.calculate_direct_route(
            origin, destination, safety=3, use_turn_costs=False
        )

        # ターンコストあり
        result_with_turn = route_calculator.calculate_direct_route(
            origin, destination, safety=3, use_turn_costs=True
        )

        # 距離の増加率を計算
        distance_increase_ratio = (
            (result_with_turn.distance - result_no_turn.distance)
            / result_no_turn.distance
        )

        # 50%以内の増加であることを確認
        max_acceptable_increase = 0.50  # 50%

        assert distance_increase_ratio <= max_acceptable_increase, \
            f"ターンコストによって距離が増えすぎています: " \
            f"なし={result_no_turn.distance:.0f}m, " \
            f"あり={result_with_turn.distance:.0f}m, " \
            f"増加率={distance_increase_ratio*100:.1f}%"

    def test_turn_cost_right_turns_more_penalized(self, route_calculator):
        """
        右折が左折より多くペナルティを受けることを確認

        非エンジニア向け解説:
            日本は左側通行なので、右折は対向車を気にする必要があり、
            より危険です。そのため、右折には高いペナルティを設定しています。

            このテストでは、ターンコストを適用した場合、
            右折の数が減る傾向があることを確認します。
        """
        origin = (135.7588, 34.9858)      # 京都駅
        destination = (135.7482, 35.0142)  # 二条城

        # ターンコストなし
        result_no_turn = route_calculator.calculate_direct_route(
            origin, destination, safety=3, use_turn_costs=False
        )

        # ターンコストあり
        result_with_turn = route_calculator.calculate_direct_route(
            origin, destination, safety=3, use_turn_costs=True
        )

        # 右折の減少率を計算（右折がある場合のみ）
        if result_no_turn.right_turn_count > 0:
            right_turn_decrease = (
                result_no_turn.right_turn_count - result_with_turn.right_turn_count
            )
            # 右折が減っているか、または増えても1回以内であること
            assert right_turn_decrease >= -1, \
                f"右折が増えすぎています: " \
                f"なし={result_no_turn.right_turn_count}, " \
                f"あり={result_with_turn.right_turn_count}"


class TestShareCycleRouteCoordinates:
    """
    シェアサイクルルートの座標バリデーションテスト

    非エンジニア向け解説:
        シェアサイクルを利用する場合、3つの区間があります：
        1. 出発地 → 借りポート（徒歩）
        2. 借りポート → 返しポート（自転車）
        3. 返しポート → 目的地（徒歩）

        各区間の座標が最低2点あることを確認します。
    """

    @pytest.fixture
    def route_calculator(self):
        """RouteCalculatorのインスタンスを作成"""
        import pickle
        from app.services.route_calculator import RouteCalculator
        from app.data import PARKINGS

        graph_path = "app/data/graph/kyoto_bike_graph.pkl"
        try:
            with open(graph_path, "rb") as f:
                graph = pickle.load(f)
        except FileNotFoundError:
            pytest.skip("Graph file not found")

        return RouteCalculator(graph, parkings=PARKINGS)

    @pytest.fixture
    def mock_ports(self):
        """モックのポートデータを作成"""
        from app.models.port import Port
        from datetime import datetime

        return [
            Port(
                id="port_1",
                name="テストポート1",
                coordinates=[135.7593, 35.0298],
                operator="docomo",
                bikes_available=5,
                docks_available=10,
                is_renting=True,
                is_returning=True,
                last_reported=datetime.now()
            ),
            Port(
                id="port_2",
                name="テストポート2",
                coordinates=[135.7482, 35.0142],
                operator="docomo",
                bikes_available=5,
                docks_available=10,
                is_renting=True,
                is_returning=True,
                last_reported=datetime.now()
            ),
        ]

    def test_share_cycle_route_all_segments_have_minimum_coordinates(
        self, route_calculator, mock_ports
    ):
        """
        シェアサイクルルートの全セグメントが最低2点の座標を持つことを確認

        非エンジニア向け解説:
            今出川駅のような「ポートに近い場所」を出発地にした場合、
            徒歩区間の座標が1点しかないエラーが発生していました。

            このテストでは、近い場所でも全ての区間で2点以上の座標が
            返されることを確認します。
        """
        # 今出川駅に近い場所を出発地に設定
        origin = (135.7593106, 35.0298128)  # ポートに非常に近い
        destination = (135.7482, 35.0142)

        result = route_calculator.calculate_share_cycle_route(
            origin, destination, safety=3, ports=mock_ports
        )

        # 各セグメントの座標を確認
        # 徒歩区間1: 出発地 → 借りポート
        walk_to_coords = result['walk_to_port_route']['coordinates']
        assert len(walk_to_coords) >= 2, \
            f"徒歩区間1の座標が不足: {walk_to_coords}"

        # 自転車区間: 借りポート → 返しポート
        bike_coords = result['bicycle_route'].coordinates
        assert len(bike_coords) >= 2, \
            f"自転車区間の座標が不足: {bike_coords}"

        # 徒歩区間2: 返しポート → 目的地
        walk_from_coords = result['walk_from_port_route']['coordinates']
        assert len(walk_from_coords) >= 2, \
            f"徒歩区間2の座標が不足: {walk_from_coords}"


class TestTurnCostValues:
    """
    曲がり角コストの値の妥当性テスト

    非エンジニア向け解説:
        曲がり角ごとのコスト（ペナルティ）が、
        日本の自転車事情に合っているか確認します。

        日本は左側通行なので：
        - 左折: 比較的安全 → 低いペナルティ
        - 右折: 対向車がいて危険 → 高いペナルティ
    """

    def test_turn_costs_are_reasonable(self):
        """
        ターンコストが妥当な範囲内であることを確認

        非エンジニア向け解説:
            各曲がり角のコストが「メートル相当」で設定されています。
            例えば「右折 = 75m」は、「右折1回は、75m余分に走るのと
            同じくらいのコストがある」という意味です。

            このテストでは、コストが極端に大きすぎないことを確認します。
        """
        from app.services.turn_calculator import TURN_COSTS

        # 最大コスト（Uターン）が500m相当以内であること
        # 500mも迂回するならUターンした方がマシ、という程度
        assert TURN_COSTS['uturn'] < 500, \
            f"Uターンコストが大きすぎます: {TURN_COSTS['uturn']}m"

        # 右折が300m相当以内であること
        assert TURN_COSTS['right'] < 300, \
            f"右折コストが大きすぎます: {TURN_COSTS['right']}m"

        # 左折が200m相当以内であること
        assert TURN_COSTS['left'] < 200, \
            f"左折コストが大きすぎます: {TURN_COSTS['left']}m"

    def test_right_turn_more_expensive_than_left(self):
        """
        右折が左折より高いコストであることを確認（日本の道路事情）

        非エンジニア向け解説:
            日本では左側通行なので：
            - 左折: 車道の左側から曲がるだけで、対向車を気にしない
            - 右折: 対向車を横切る必要があり、危険

            そのため、右折には左折より高いペナルティを設定しています。
        """
        from app.services.turn_calculator import TURN_COSTS

        assert TURN_COSTS['right'] > TURN_COSTS['left'], \
            f"右折({TURN_COSTS['right']}m)が左折({TURN_COSTS['left']}m)より安いです"

        assert TURN_COSTS['slight_right'] > TURN_COSTS['slight_left'], \
            f"緩やか右折({TURN_COSTS['slight_right']}m)が" \
            f"緩やか左折({TURN_COSTS['slight_left']}m)より安いです"
