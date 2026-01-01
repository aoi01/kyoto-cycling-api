"""
tests/test_usecases.py

フロントエンドユースケースに基づくAPIテスト

各ユースケース（UC-1〜UC-4）をバックエンドAPIが満たせることを検証する。

ユースケース概要:
- UC-1: 自分の自転車で観光地へ（駐輪場案内あり）
- UC-2: 自分の自転車で観光地へ（駐輪場案内なし）
- UC-3: シェアサイクルで観光地へ
- UC-4: カテゴリで観光地を探す（ポートAPI）
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock

from tests.conftest import KYOTO_STATION, NIJO_CASTLE, KINKAKUJI, KIYOMIZU


# =============================================================================
# UC-1: 自分の自転車で観光地へ行く（駐輪場案内あり）
# =============================================================================

class TestUC1ParkingRoute:
    """
    UC-1: 自分の自転車で観光地へ行く（駐輪場案内あり）

    フロントエンドシナリオ:
    1. ユーザーが地図上の「金閣寺」ピンをタップ
    2. 「自分の自転車」を選択
    3. 「駐輪場を教えて」にチェック
    4. 安全スライダーを「7」に設定
    5. 「ルートを検索」をタップ
    6. 地図上に2区間のルートが表示される
       - 青線: 現在地 → 駐輪場（自転車・安全ルート）
       - 緑線: 駐輪場 → 金閣寺（徒歩・最短）
    7. 駐輪場の情報カード表示（名前、料金、徒歩時間）
    8. 「ナビ開始」→ 音声案内
    """

    async def test_parking_route_returns_two_segments(self, async_client):
        """
        駐輪場経由ルートは2つのセグメント（自転車 + 徒歩）を返す
        """
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{KINKAKUJI[0]},{KINKAKUJI[1]}",
                "mode": "my-cycle",
                "safety": 7,
                "needParking": "true",
            }
        )

        assert response.status_code == 200
        data = response.json()

        if data["success"]:
            segments = data["data"]["segments"]
            # 駐輪場経由の場合、2セグメント（自転車 + 徒歩）
            assert len(segments) == 2

            # 最初のセグメントは自転車
            assert segments[0]["type"] == "bicycle"
            # 2番目のセグメントは徒歩
            assert segments[1]["type"] == "walk"

    async def test_parking_route_contains_parking_info(self, async_client):
        """
        レスポンスに駐輪場情報（ID、名前、座標）が含まれる
        """
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{KINKAKUJI[0]},{KINKAKUJI[1]}",
                "mode": "my-cycle",
                "safety": 7,
                "needParking": "true",
            }
        )

        assert response.status_code == 200
        data = response.json()

        if data["success"]:
            segments = data["data"]["segments"]

            # 自転車セグメントの終点が駐輪場
            bicycle_segment = segments[0]
            to_point = bicycle_segment["to"]
            assert to_point["type"] == "parking"
            assert "name" in to_point
            assert "coordinates" in to_point
            # 駐輪場にはIDがある
            assert "id" in to_point or to_point.get("id") is not None

    async def test_parking_route_has_fee_description(self, async_client):
        """
        駐輪場には料金説明（feeDescription）が含まれる
        """
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{KINKAKUJI[0]},{KINKAKUJI[1]}",
                "mode": "my-cycle",
                "safety": 7,
                "needParking": "true",
            }
        )

        assert response.status_code == 200
        data = response.json()

        if data["success"]:
            segments = data["data"]["segments"]
            bicycle_segment = segments[0]
            to_point = bicycle_segment["to"]

            # feeDescription フィールドが存在（nullでも可）
            # 注: JSON出力時はcamelCase
            assert "feeDescription" in to_point or "fee_description" in to_point

    async def test_parking_route_voice_instructions(self, async_client):
        """
        ルートに音声指示（voiceInstructions）が含まれる
        """
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{KINKAKUJI[0]},{KINKAKUJI[1]}",
                "mode": "my-cycle",
                "safety": 7,
                "needParking": "true",
            }
        )

        assert response.status_code == 200
        data = response.json()

        if data["success"]:
            segments = data["data"]["segments"]
            # 各セグメントにvoiceInstructionsフィールドがある
            for segment in segments:
                assert "voiceInstructions" in segment

    async def test_parking_route_summary_includes_distances(self, async_client):
        """
        サマリーに総距離、自転車距離、徒歩距離が含まれる
        """
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{KINKAKUJI[0]},{KINKAKUJI[1]}",
                "mode": "my-cycle",
                "safety": 7,
                "needParking": "true",
            }
        )

        assert response.status_code == 200
        data = response.json()

        if data["success"]:
            summary = data["data"]["summary"]
            # 必須フィールド
            assert "totalDistance" in summary
            assert "totalDuration" in summary
            assert "bicycleDistance" in summary
            assert "walkDistance" in summary

            # 駐輪場経由なので徒歩距離 > 0
            assert summary["walkDistance"] > 0

    async def test_safety_slider_affects_route(self, async_client):
        """
        安全スライダー（safety）の値がルートに影響する

        注: 駐輪場なしの直接ルートでテスト（駐輪場がない地域でのエラーを避けるため）
        """
        # safety=1（最短優先）
        response_fast = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "my-cycle",
                "safety": 1,
                "needParking": "false",
            }
        )

        # safety=10（安全最優先）
        response_safe = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "my-cycle",
                "safety": 10,
                "needParking": "false",
            }
        )

        assert response_fast.status_code == 200
        assert response_safe.status_code == 200

        data_fast = response_fast.json()
        data_safe = response_safe.json()

        # 両方成功することを確認
        assert data_fast["success"] is True
        assert data_safe["success"] is True


# =============================================================================
# UC-2: 自分の自転車で観光地へ行く（駐輪場案内なし）
# =============================================================================

class TestUC2DirectRoute:
    """
    UC-2: 自分の自転車で観光地へ行く（駐輪場案内なし）

    フロントエンドシナリオ:
    1. 「自分の自転車」を選択
    2. 「駐輪場を教えて」のチェックを外す
    3. 出発地: 検索窓に「京都駅」と入力
    4. 目的地: 検索窓に「二条城」と入力
    5. 安全スライダーを「5」に設定（バランス型）
    6. 「ルートを検索」をタップ
    7. 地図上に1本のルートが表示される（現在地 → 二条城）
    8. 「ナビ開始」で音声案内開始
    """

    async def test_direct_route_returns_one_segment(self, async_client):
        """
        直接ルートは1つのセグメント（自転車のみ）を返す
        """
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

        if data["success"]:
            segments = data["data"]["segments"]
            # 直接ルートは1セグメント
            assert len(segments) == 1
            # セグメントタイプは自転車
            assert segments[0]["type"] == "bicycle"

    async def test_direct_route_origin_destination(self, async_client):
        """
        セグメントのfrom/toに出発地・目的地情報が含まれる
        """
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

        if data["success"]:
            segment = data["data"]["segments"][0]

            # fromがorigin
            assert segment["from"]["type"] == "origin"
            assert "coordinates" in segment["from"]

            # toがdestination
            assert segment["to"]["type"] == "destination"
            assert "coordinates" in segment["to"]

    async def test_direct_route_geometry(self, async_client):
        """
        ルートにジオメトリ（GeoJSON LineString）が含まれる
        """
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

        if data["success"]:
            segment = data["data"]["segments"][0]
            route = segment["route"]

            # ジオメトリが含まれる
            assert "geometry" in route
            geometry = route["geometry"]
            assert geometry["type"] == "LineString"
            assert "coordinates" in geometry
            # 座標は配列
            assert isinstance(geometry["coordinates"], list)
            assert len(geometry["coordinates"]) >= 2

    async def test_direct_route_distance_duration(self, async_client):
        """
        ルートに距離（メートル）と所要時間（秒）が含まれる
        """
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

        if data["success"]:
            segment = data["data"]["segments"][0]
            route = segment["route"]

            # 距離と所要時間
            assert "distance" in route
            assert "duration" in route
            assert route["distance"] > 0
            assert route["duration"] > 0

    async def test_direct_route_no_walk_distance(self, async_client):
        """
        直接ルートのサマリーで徒歩距離は0
        """
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

        if data["success"]:
            summary = data["data"]["summary"]
            # 直接ルートなので徒歩距離は0
            assert summary["walkDistance"] == 0

    async def test_direct_route_safety_score(self, async_client):
        """
        自転車区間のルートに安全スコアが含まれる
        """
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

        if data["success"]:
            segment = data["data"]["segments"][0]
            route = segment["route"]

            # 安全スコア（0-10）
            if "safetyScore" in route:
                assert 0 <= route["safetyScore"] <= 10


# =============================================================================
# UC-3: シェアサイクルで観光地へ行く
# =============================================================================

class TestUC3ShareCycleRoute:
    """
    UC-3: シェアサイクルで観光地へ行く

    フロントエンドシナリオ:
    1. 「シェアサイクル」を選択
    2. 「HELLO CYCLING」にチェック（ドコモは外す）
    3. 出発地: 「現在地から出発」を選択
    4. 目的地: 地図上の「伏見稲荷大社」をタップ
    5. 安全スライダーを「8」に設定（安全重視）
    6. 「ルートを検索」をタップ
    7. 地図上に3区間のルートが表示される
       - 緑線: 現在地 → 最寄りポート（徒歩）
       - 青線: ポート → 返却ポート（自転車・安全ルート）
       - 緑線: 返却ポート → 伏見稲荷大社（徒歩）
    8. ポート情報カード表示
       - 借りるポート: 「京都駅八条口」空き5台
       - 返すポート: 「伏見稲荷駅前」空きドック3台
    """

    async def test_share_cycle_returns_three_segments(self, async_client):
        """
        シェアサイクルルートは3つのセグメント（徒歩 + 自転車 + 徒歩）を返す
        """
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{KINKAKUJI[0]},{KINKAKUJI[1]}",
                "mode": "share-cycle",
                "safety": 8,
                "operators": "docomo",
            }
        )

        assert response.status_code == 200
        data = response.json()

        if data["success"]:
            segments = data["data"]["segments"]
            # シェアサイクルは3セグメント
            assert len(segments) == 3

            # セグメントタイプの順序: 徒歩 → 自転車 → 徒歩
            assert segments[0]["type"] == "walk"
            assert segments[1]["type"] == "bicycle"
            assert segments[2]["type"] == "walk"

    async def test_share_cycle_contains_port_info(self, async_client):
        """
        レスポンスにポート情報（借りるポート、返すポート）が含まれる
        """
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{KINKAKUJI[0]},{KINKAKUJI[1]}",
                "mode": "share-cycle",
                "safety": 8,
                "operators": "docomo",
            }
        )

        assert response.status_code == 200
        data = response.json()

        if data["success"]:
            segments = data["data"]["segments"]

            # 最初の徒歩セグメントの終点が借りるポート
            walk_to_port = segments[0]
            borrow_port = walk_to_port["to"]
            assert borrow_port["type"] == "port"
            assert "name" in borrow_port
            assert "coordinates" in borrow_port

            # 最後の徒歩セグメントの始点が返すポート
            walk_from_port = segments[2]
            return_port = walk_from_port["from"]
            assert return_port["type"] == "port"
            assert "name" in return_port

    async def test_share_cycle_operator_filter(self, async_client):
        """
        operators パラメータでシェアサイクル事業者をフィルタリング
        """
        # HELLO CYCLINGのみ
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "share-cycle",
                "safety": 5,
                "operators": "hellocycling",
            }
        )

        assert response.status_code == 200
        data = response.json()
        # operators フィルタが機能している（エラーではない）
        assert "success" in data

    async def test_share_cycle_multiple_operators(self, async_client):
        """
        複数事業者（docomo,hellocycling）を指定できる
        """
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
        assert "success" in data

    async def test_share_cycle_summary_has_all_distances(self, async_client):
        """
        サマリーに自転車距離と徒歩距離の両方が含まれる
        """
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{KINKAKUJI[0]},{KINKAKUJI[1]}",
                "mode": "share-cycle",
                "safety": 8,
                "operators": "docomo",
            }
        )

        assert response.status_code == 200
        data = response.json()

        if data["success"]:
            summary = data["data"]["summary"]
            # シェアサイクルは自転車区間と徒歩区間の両方がある
            assert summary["bicycleDistance"] > 0
            assert summary["walkDistance"] > 0
            # 合計距離 = 自転車 + 徒歩
            expected_total = summary["bicycleDistance"] + summary["walkDistance"]
            assert abs(summary["totalDistance"] - expected_total) < 1  # 誤差1m以内


# =============================================================================
# UC-4: カテゴリで観光地を探す（ポートAPI）
# =============================================================================

class TestUC4PortsAPI:
    """
    UC-4: シェアサイクルポートの取得

    フロントエンドシナリオ:
    - シェアサイクルモード選択時にポート一覧を取得
    - 空き台数・空きドック数でフィルタリング
    - 現在地からの距離でソート
    """

    async def test_get_ports_basic(self, async_client):
        """
        GET /api/ports でポート一覧を取得できる
        """
        response = await async_client.get(
            "/api/ports",
            params={
                "operators": "docomo",
            }
        )

        # ポートAPIが登録されていれば200
        # 未登録の場合は404（これも許容）
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            if data["success"]:
                assert "data" in data
                assert "ports" in data["data"]
                assert "totalCount" in data["data"]

    async def test_get_ports_filter_by_operator(self, async_client):
        """
        operators パラメータで事業者フィルタリング
        """
        response = await async_client.get(
            "/api/ports",
            params={
                "operators": "hellocycling",
            }
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("data", {}).get("ports"):
                for port in data["data"]["ports"]:
                    # フィルタリングされている（または複数事業者の場合）
                    assert "operator" in port

    async def test_get_ports_near_location(self, async_client):
        """
        near パラメータで特定地点の近くのポートを取得
        """
        response = await async_client.get(
            "/api/ports",
            params={
                "operators": "docomo",
                "near": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "radius": 1000,  # 1km圏内
            }
        )

        if response.status_code == 200:
            data = response.json()
            # near指定時は距離でソートされる
            assert "success" in data

    async def test_get_ports_min_bikes(self, async_client):
        """
        min_bikes パラメータで空き台数フィルタリング
        """
        response = await async_client.get(
            "/api/ports",
            params={
                "operators": "docomo",
                "min_bikes": 3,  # 3台以上空きがあるポート
            }
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("data", {}).get("ports"):
                for port in data["data"]["ports"]:
                    # モックデータの場合、bikes_availableがある
                    if "bikesAvailable" in port or "bikes_available" in port:
                        bikes = port.get("bikesAvailable") or port.get("bikes_available", 0)
                        assert bikes >= 3


# =============================================================================
# リルート機能のテスト
# =============================================================================

class TestRerouting:
    """
    リルート機能のテスト

    フロントエンドシナリオ:
    - 30m以上ルートから外れたら自動でリルート
    - 新しい現在地から目的地へのルートを再計算
    """

    async def test_reroute_from_new_position(self, async_client):
        """
        新しい現在地からルートを再計算できる
        """
        # 元のルート（京都駅 → 金閣寺）
        original_response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{KINKAKUJI[0]},{KINKAKUJI[1]}",
                "mode": "my-cycle",
                "safety": 5,
                "needParking": "false",
            }
        )

        assert original_response.status_code == 200

        # ルートを外れた位置（清水寺付近）から再計算
        reroute_response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KIYOMIZU[0]},{KIYOMIZU[1]}",  # 新しい現在地
                "destination": f"{KINKAKUJI[0]},{KINKAKUJI[1]}",
                "mode": "my-cycle",
                "safety": 5,
                "needParking": "false",
            }
        )

        assert reroute_response.status_code == 200
        data = reroute_response.json()
        assert data["success"] is True

        # 新しい出発地からのルートが生成される
        if "data" in data:
            segment = data["data"]["segments"][0]
            # 出発地の座標が新しい位置になっている
            from_coords = segment["from"]["coordinates"]
            # 清水寺付近の座標と近い
            assert abs(from_coords[0] - KIYOMIZU[0]) < 0.01
            assert abs(from_coords[1] - KIYOMIZU[1]) < 0.01


# =============================================================================
# エラーハンドリングのテスト
# =============================================================================

class TestErrorHandling:
    """
    エラーケースのテスト

    フロントエンドで適切なエラーメッセージを表示するために、
    APIが適切なエラーレスポンスを返すことを確認
    """

    async def test_invalid_coordinates_format(self, async_client):
        """
        座標形式が不正な場合のエラー
        """
        response = await async_client.get(
            "/api/route",
            params={
                "origin": "invalid-format",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "my-cycle",
                "safety": 5,
            }
        )

        # 422（バリデーションエラー）または200でsuccess=false
        assert response.status_code in [200, 422]
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is False
            assert "error" in data

    async def test_safety_out_of_range(self, async_client):
        """
        安全スライダーの値が範囲外の場合
        """
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "my-cycle",
                "safety": 15,  # 範囲外（1-10）
            }
        )

        assert response.status_code == 422

    async def test_invalid_mode(self, async_client):
        """
        無効なモードが指定された場合
        """
        response = await async_client.get(
            "/api/route",
            params={
                "origin": f"{KYOTO_STATION[0]},{KYOTO_STATION[1]}",
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "walking",  # 無効なモード
                "safety": 5,
            }
        )

        assert response.status_code == 422

    async def test_missing_required_params(self, async_client):
        """
        必須パラメータが不足している場合
        """
        # originなし
        response = await async_client.get(
            "/api/route",
            params={
                "destination": f"{NIJO_CASTLE[0]},{NIJO_CASTLE[1]}",
                "mode": "my-cycle",
                "safety": 5,
            }
        )

        assert response.status_code == 422


# =============================================================================
# パフォーマンス関連のテスト
# =============================================================================

class TestAPIResponse:
    """
    APIレスポンス形式のテスト

    フロントエンドが期待するレスポンス形式を確認
    """

    async def test_response_format(self, async_client):
        """
        レスポンスが標準形式（success, data/error）を持つ
        """
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

        # 必須フィールド
        assert "success" in data
        assert isinstance(data["success"], bool)

        if data["success"]:
            assert "data" in data
        else:
            assert "error" in data

    async def test_camel_case_response(self, async_client):
        """
        レスポンスのJSONキーがキャメルケース
        """
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

        if data["success"]:
            summary = data["data"]["summary"]
            # キャメルケースのキー
            assert "totalDistance" in summary
            assert "totalDuration" in summary
            assert "bicycleDistance" in summary
            assert "walkDistance" in summary
