"""
app/services/voice_generator.py

自前の音声案内生成

ルート座標とグラフ情報から、曲がり角を検出して日本語の音声案内を生成。
Mapbox Directions APIに依存しないシンプルな実装。

アルゴリズム:
1. ルート座標から曲がり角を検出（角度変化30度以上）
2. 各曲がり角で方向を判定（右折/左折/Uターン）
3. 累積距離から案内テキストを生成
4. 50m手前から案内を開始

参照:
- 方位角計算: https://en.wikipedia.org/wiki/Bearing_(navigation)
"""
import math
from dataclasses import dataclass
from typing import Optional

from app.models.route import VoiceInstruction


@dataclass
class TurnPoint:
    """曲がり角情報"""
    index: int                      # ルート座標配列内のインデックス
    coordinates: tuple[float, float]  # [経度, 緯度]
    bearing_before: float           # この点に入る前の方位角（0-360度）
    bearing_after: float            # この点を出た後の方位角（0-360度）
    angle_diff: float               # 角度差（0-180度）


def _calculate_bearing(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    2点間の方位角（bearing）を計算（度数法、0-360）

    北を0度として時計回りに角度を返す。

    Args:
        lon1, lat1: 始点の経度・緯度
        lon2, lat2: 終点の経度・緯度

    Returns:
        方位角（0-360度）
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lon = math.radians(lon2 - lon1)

    x = math.sin(delta_lon) * math.cos(lat2_rad)
    y = (math.cos(lat1_rad) * math.sin(lat2_rad) -
         math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon))

    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def _angle_difference(bearing1: float, bearing2: float) -> float:
    """
    2つの方位角の差を計算（0-180度）

    Args:
        bearing1, bearing2: 方位角（0-360度）

    Returns:
        角度差（0-180度）
    """
    diff = abs(bearing1 - bearing2)
    return min(diff, 360 - diff)


def _bearing_change(bearing_before: float, bearing_after: float) -> float:
    """
    方位角の変化を計算（-180 ~ 180度）

    正の値 = 右回転、負の値 = 左回転

    Args:
        bearing_before: 最初の方位角
        bearing_after: 後の方位角

    Returns:
        方位角の変化（-180 ~ 180度）
    """
    change = bearing_after - bearing_before

    # -180 ~ 180度の範囲に正規化
    if change > 180:
        change -= 360
    elif change < -180:
        change += 360

    return change


def _haversine_distance(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    Haversine距離（メートル）

    Args:
        lon1, lat1: 始点の経度・緯度
        lon2, lat2: 終点の経度・緯度

    Returns:
        距離（メートル）
    """
    R = 6_371_000  # 地球の半径（メートル）
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


class VoiceInstructionGenerator:
    """自前の音声案内生成"""

    ANGLE_THRESHOLD = 30.0  # 曲がり角と判定する角度閾値（度）
    ANNOUNCEMENT_DISTANCE = 50.0  # 案内を開始する距離（メートル）
    TURN_DIRECTION_THRESHOLD = 30.0  # 左右判定の境界（度）

    @staticmethod
    def _detect_turn_points(
        coordinates: list[list[float]],
        angle_threshold: float = ANGLE_THRESHOLD,
    ) -> list[TurnPoint]:
        """
        ルート座標から曲がり角を検出

        Args:
            coordinates: ルート座標 [[経度, 緯度], ...]
            angle_threshold: 曲がり角と判定する角度差の閾値（度）

        Returns:
            曲がり角リスト
        """
        if len(coordinates) < 3:
            return []

        turn_points = []

        for i in range(1, len(coordinates) - 1):
            prev = coordinates[i - 1]
            curr = coordinates[i]
            next_ = coordinates[i + 1]

            # 方位角を計算
            bearing_before = _calculate_bearing(prev[0], prev[1], curr[0], curr[1])
            bearing_after = _calculate_bearing(curr[0], curr[1], next_[0], next_[1])

            # 角度差が閾値を超えたら曲がり角
            angle_diff = _angle_difference(bearing_before, bearing_after)
            if angle_diff >= angle_threshold:
                turn_points.append(TurnPoint(
                    index=i,
                    coordinates=(curr[0], curr[1]),
                    bearing_before=bearing_before,
                    bearing_after=bearing_after,
                    angle_diff=angle_diff,
                ))

        return turn_points

    @staticmethod
    def _determine_turn_direction(turn_point: TurnPoint) -> str:
        """
        曲がり角の方向を判定

        Args:
            turn_point: 曲がり角情報

        Returns:
            方向（"左折", "右折", "Uターン"）
        """
        angle_diff = turn_point.angle_diff
        change = _bearing_change(turn_point.bearing_before, turn_point.bearing_after)

        # Uターン判定（150度以上の角度変化）
        if angle_diff >= 150:
            return "Uターン"

        # 左右判定（角度差30度以上で左または右）
        if abs(change) > 45:  # 45度以上で明確に左右
            if change > 0:
                return "右折"
            else:
                return "左折"

        # 45度未満の場合は、より小さな変化で判定
        if change > 0:
            return "右折"
        else:
            return "左折"

    @staticmethod
    def _generate_announcement(distance: float, direction: str) -> str:
        """
        案内テキストを生成

        Args:
            distance: 次の曲がり角までの距離（メートル）
            direction: "左折" | "右折" | "Uターン"

        Returns:
            案内テキスト
        """
        # 距離によって案内文を変える
        if distance > 200:
            return f"{int(distance)}メートル先を{direction}してください"
        elif distance > 100:
            return f"約{int(distance)}メートル先を{direction}"
        elif distance > 50:
            return f"{int(distance)}メートル先を{direction}"
        else:
            # 50m以内は「次」という表現
            if direction == "Uターン":
                return "Uターンしてください"
            else:
                return f"次の交差点を{direction}してください"

    @classmethod
    def generate_instructions(
        cls,
        coordinates: list[list[float]],
    ) -> list[VoiceInstruction]:
        """
        ルート座標から音声案内を生成

        改善点:
        1. 累積距離を一度だけ計算し、各曲がり角では参照のみ
        2. 曲がり角までの実際の距離で案内テキストを生成
        3. 50m手前で案内を開始し、その距離で「○○メートル先」と案内
        4. 重複排除時は実際の距離値を使用（丸め込みなし）

        Args:
            coordinates: ルート座標 [[経度, 緯度], ...]

        Returns:
            音声案内リスト
        """
        if len(coordinates) < 3:
            # 最後の「目的地に到着しました」のみ
            return [VoiceInstruction(
                distance_along_geometry=0,
                announcement="目的地に到着しました",
            )]

        # 累積距離を事前計算（インデックス i は coordinates[i] から coordinates[i+1] までの距離）
        cumulative_distances = [0.0]
        for j in range(len(coordinates) - 1):
            lon1, lat1 = coordinates[j]
            lon2, lat2 = coordinates[j + 1]
            dist = _haversine_distance(lon1, lat1, lon2, lat2)
            cumulative_distances.append(cumulative_distances[-1] + dist)

        total_distance = cumulative_distances[-1]

        # 曲がり角を検出
        turn_points = cls._detect_turn_points(coordinates)

        if not turn_points:
            # 曲がり角がない場合は、最後の案内のみ
            return [VoiceInstruction(
                distance_along_geometry=total_distance,
                announcement="目的地に到着しました",
            )]

        instructions = []

        # 各曲がり角に対して案内を生成
        for turn_point in turn_points:
            # 曲がり角の方向を判定
            direction = cls._determine_turn_direction(turn_point)

            # 曲がり角までの距離（事前計算した累積距離から参照）
            distance_to_turn = cumulative_distances[turn_point.index]

            # ルート総距離を超えないようにクリップ
            distance_to_turn = min(distance_to_turn, total_distance)

            # 曲がり角までの距離が10m以上の場合のみ案内を生成
            # （非常に短い距離では案内の意味がないため）
            if distance_to_turn >= 10:
                # 案内を開始する距離（曲がり角の50m手前）
                # ただし、0より小さくならないように調整
                announcement_distance = max(0, distance_to_turn - cls.ANNOUNCEMENT_DISTANCE)

                # 案内テキストに使う「残り距離」は、実際に50m手前で案内する場合は50m
                # 50m未満の場合は実際の距離をそのまま使用
                remaining_distance = min(cls.ANNOUNCEMENT_DISTANCE, distance_to_turn)

                announcement = cls._generate_announcement(
                    remaining_distance,
                    direction
                )
                instructions.append(VoiceInstruction(
                    distance_along_geometry=announcement_distance,
                    announcement=announcement,
                ))

        # 最後に「目的地に到着しました」を追加
        instructions.append(VoiceInstruction(
            distance_along_geometry=total_distance,
            announcement="目的地に到着しました",
        ))

        # 距離順にソート
        instructions.sort(key=lambda x: x.distance_along_geometry)

        # 同じ距離の重複を排除（距離値で直接比較、差分1m未満）
        unique_instructions = []
        last_distance = -float('inf')
        for inst in instructions:
            # 前の案内との距離差が1m以上の場合のみ追加
            if inst.distance_along_geometry - last_distance >= 1.0:
                unique_instructions.append(inst)
                last_distance = inst.distance_along_geometry

        return unique_instructions
