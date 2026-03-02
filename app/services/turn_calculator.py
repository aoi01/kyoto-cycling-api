"""
app/services/turn_calculator.py

ターン（曲がり角）のコスト計算ユーティリティ

自転車での走行において、曲がることのリスクをコストとして計算。
特に日本（左側通行）では右折が危険なため、高いペナルティを設定。

使用例:
    angle = calculate_turn_angle(prev_edge, current_edge)
    turn_type = classify_turn(angle)
    cost = get_turn_cost(turn_type)
"""
import math
from typing import Optional, Tuple


# =============================================================================
# ターンコスト定数
# =============================================================================

# ターンの種類ごとのコスト（メートル相当）
# 「この曲がり角を通ることは、○○メートル余分に走るのと同じコスト」
# 2024/03/02: コストを1.5倍に調整
TURN_COSTS = {
    'straight': 0,       # 直進：ペナルティなし
    'slight_left': 15,   # 左へ緩やか：15m相当（10→15）
    'left': 38,          # 左折：38m相当（25→38）
    'sharp_left': 60,    # 左へ急カーブ：60m相当（40→60）
    'slight_right': 30,  # 右へ緩やか：30m相当（20→30）
    'right': 75,         # 右折：75m相当（50→75）日本では危険！
    'sharp_right': 120,  # 右へ急カーブ：120m相当（80→120）
    'uturn': 225,        # Uターン：225m相当（150→225）
}

# ターン分類の角度閾値（度）
# 直進からの角度で分類
TURN_THRESHOLDS = {
    'straight': 22.5,      # 0-22.5° は直進とみなす
    'slight': 45,          # 22.5-45° は緩やかな曲がり
    'normal': 135,         # 45-135° は通常の曲がり
    'sharp': 180,          # 135-180° は急カーブ/Uターン
}


# =============================================================================
# 方位角計算
# =============================================================================

def calculate_bearing(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    2点間の方位角（進行方向）を計算

    方位角とは：
        北を0°とし、時計回りに測った角度
        - 北: 0°
        - 東: 90°
        - 南: 180°
        - 西: 270°

    Args:
        lon1: 始点の経度
        lat1: 始点の緯度
        lon2: 終点の経度
        lat2: 終点の緯度

    Returns:
        方位角（0-360度）

    非エンジニア向け解説:
        「A地点からB地点に向かうとき、どの方角を向いているか」を計算
    """
    # 緯度経度をラジアンに変換
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)

    # 方位角の計算
    x = math.sin(dlon) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - \
        math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon)

    bearing = math.atan2(x, y)

    # -180〜180° を 0〜360° に変換
    bearing_deg = math.degrees(bearing)
    return (bearing_deg + 360) % 360


def calculate_turn_angle(bearing_in: float, bearing_out: float) -> float:
    """
    曲がり角の角度を計算

    Args:
        bearing_in: 进入時の方位角（どこから来たか）
        bearing_out: 出る時の方位角（どこへ行くか）

    Returns:
        曲がり角の角度（0-180度）
        - 0° = 直進
        - 90° = 直角に曲がる
        - 180° = Uターン

    非エンジニア向け解説:
        「道に入ってきた方向」と「出ていく方向」の差を計算
        0度なら全く曲がっていない（直進）
        180度なら来た道を逆戻り（Uターン）
    """
    # 方位角の差を計算
    diff = bearing_out - bearing_in

    # -180〜180° の範囲に正規化
    # 例: 350° → 10°、-170° → 170°
    while diff > 180:
        diff -= 360
    while diff < -180:
        diff += 360

    # 絶対値を返す（左折も右折も正の値として扱う）
    return abs(diff)


# =============================================================================
# ターン分類
# =============================================================================

def classify_turn(turn_angle: float) -> str:
    """
    曲がり角の角度から、ターンの種類を分類

    Args:
        turn_angle: 曲がり角の角度（0-180度）

    Returns:
        ターンの種類:
        - 'straight': 直進（ほぼ曲がっていない）
        - 'slight_left'/'slight_right': 緩やかなカーブ
        - 'left'/'right': 通常の曲がり
        - 'sharp_left'/'sharp_right': 急カーブ
        - 'uturn': Uターン

    非エンジニア向け解説:
        「どのくらい曲がっているか」をカテゴリに分ける
        信号待ちで「右折レーン」に入るような曲がり方は 'right'
    """
    # 直進（ほとんど曲がらない）
    if turn_angle <= TURN_THRESHOLDS['straight']:
        return 'straight'

    # 緩やかなカーブ
    if turn_angle <= TURN_THRESHOLDS['slight']:
        # 左か右かは呼び出し元で判断（ここでは角度のみ）
        return 'slight'

    # 通常の曲がり
    if turn_angle <= TURN_THRESHOLDS['normal']:
        return 'normal'

    # 急カーブ / Uターン
    return 'sharp'


def classify_turn_with_direction(
    turn_angle: float,
    bearing_in: float,
    bearing_out: float
) -> str:
    """
    曲がり角の角度と方向から、詳細なターンの種類を分類

    Args:
        turn_angle: 曲がり角の角度（0-180度）
        bearing_in: 进入時の方位角
        bearing_out: 出る時の方位角

    Returns:
        ターンの種類（右折/左折を区別）

    非エンジニア向け解説:
        角度だけでなく「右に曲がるか、左に曲がるか」も判断
        日本では右折が危険（車が後ろから来るため）
    """
    if turn_angle <= TURN_THRESHOLDS['straight']:
        return 'straight'

    # 右折か左折かを判定
    # bearing_out - bearing_in が正なら右折、負なら左折
    diff = bearing_out - bearing_in
    while diff > 180:
        diff -= 360
    while diff < -180:
        diff += 360

    is_right_turn = diff > 0

    # 角度に応じて詳細分類
    if turn_angle <= TURN_THRESHOLDS['slight']:
        return 'slight_right' if is_right_turn else 'slight_left'
    elif turn_angle <= TURN_THRESHOLDS['normal']:
        return 'right' if is_right_turn else 'left'
    else:
        # 135°以上は急カーブまたはUターン
        if turn_angle >= 160:
            return 'uturn'
        return 'sharp_right' if is_right_turn else 'sharp_left'


# =============================================================================
# コスト取得
# =============================================================================

def get_turn_cost(turn_type: str) -> float:
    """
    ターンの種類からコスト（ペナルティ）を取得

    Args:
        turn_type: ターンの種類

    Returns:
        コスト（メートル相当）

    非エンジニア向け解説:
        「右折する」と決めた場合、どれくらいのペナルティを与えるか
        右折 = 50m余分に走るのと同じ「コスト」があるとみなす
    """
    return TURN_COSTS.get(turn_type, 0)


def calculate_turn_cost_from_bearings(
    bearing_in: float,
    bearing_out: float
) -> float:
    """
    方位角から直接ターンコストを計算（便利関数）

    Args:
        bearing_in: 进入時の方位角
        bearing_out: 出る時の方位角

    Returns:
        ターンコスト（メートル相当）
    """
    turn_angle = calculate_turn_angle(bearing_in, bearing_out)
    turn_type = classify_turn_with_direction(turn_angle, bearing_in, bearing_out)
    return get_turn_cost(turn_type)


# =============================================================================
# エッジ間のターン計算
# =============================================================================

def calculate_turn_cost_between_edges(
    prev_coords: Tuple[float, float, float, float],
    curr_coords: Tuple[float, float, float, float]
) -> float:
    """
    2つのエッジ（道路区間）間のターンコストを計算

    Args:
        prev_coords: 前のエッジの座標 (lon1, lat1, lon2, lat2)
        curr_coords: 現在のエッジの座標 (lon1, lat1, lon2, lat2)

    Returns:
        ターンコスト（メートル相当）

    非エンジニア向け解説:
        「道A」から「道B」に曲がる時のコストを計算
        prev_coords: 道Aの始点と終点
        curr_coords: 道Bの始点と終点
        （道Aの終点 = 道Bの始点 = 交差点）
    """
    prev_lon1, prev_lat1, prev_lon2, prev_lat2 = prev_coords
    curr_lon1, curr_lat1, curr_lon2, curr_lat2 = curr_coords

    # 前のエッジの進行方向
    bearing_in = calculate_bearing(prev_lon1, prev_lat1, prev_lon2, prev_lat2)

    # 現在のエッジの進行方向
    bearing_out = calculate_bearing(curr_lon1, curr_lat1, curr_lon2, curr_lat2)

    return calculate_turn_cost_from_bearings(bearing_in, bearing_out)
