"""
app/services/mapbox_client.py

Mapbox API クライアント

Map Matching API を使用して、ルートを道路ネットワークにスナップし、
音声ナビゲーション指示を取得する。

公式ドキュメント:
- Mapbox Map Matching API: https://docs.mapbox.com/api/navigation/map-matching/
- httpx AsyncClient: https://www.python-httpx.org/async/
"""
from typing import Optional
import httpx

from app.models.common import GeoJSONLineString
from app.models.route import VoiceInstruction


# =============================================================================
# 定数定義
# =============================================================================

# Mapbox API エンドポイント
MAPBOX_API_BASE = "https://api.mapbox.com"

# Map Matching API パス
# 参照: https://docs.mapbox.com/api/navigation/map-matching/
MAP_MATCHING_PATH = "/matching/v5/mapbox"

# プロファイル（移動手段）
# 参照: https://docs.mapbox.com/api/navigation/map-matching/#optional-parameters
PROFILES = {
    "cycling": "cycling",
    "walking": "walking",
    "driving": "driving",
}


# =============================================================================
# Mapboxクライアント
# =============================================================================

class MapboxClient:
    """
    Mapbox APIクライアント
    
    Map Matching API を使用して以下を提供:
    1. GPS座標を道路ネットワークにスナップ
    2. 正確な距離・所要時間を計算
    3. 音声ナビゲーション指示を生成
    
    設計根拠:
    - Map Matching API は steps=true で詳細な経路情報を取得可能
    - voice_instructions=true で音声指示を日本語で取得
    
    参照: https://docs.mapbox.com/api/navigation/map-matching/
    「Map Matching API snaps fuzzy, inaccurate traces from a GPS unit
     to the OpenStreetMap road and path network」
    
    Attributes:
        _client (httpx.AsyncClient): HTTPクライアント
        _access_token (str): Mapbox アクセストークン
    
    使用例:
        async with MapboxClient(access_token) as client:
            geometry, instructions, distance, duration = await client.map_match(
                coordinates=[(135.7588, 34.9858), (135.7500, 35.0000)],
                profile="cycling"
            )
    """
    
    def __init__(self, access_token: str):
        """
        初期化
        
        Args:
            access_token: Mapbox アクセストークン
        
        参照: https://docs.mapbox.com/api/overview/#access-tokens-and-token-scopes
        """
        self._access_token = access_token
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=10.0),
            limits=httpx.Limits(
                max_connections=50,
                max_keepalive_connections=10,
            ),
            headers={
                "User-Agent": "KyotoBikeNavi/1.0",
                "Accept": "application/json",
            },
        )
    
    async def __aenter__(self):
        """async with 文のエントリポイント"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """async with 文の終了処理"""
        await self.close()
    
    async def close(self):
        """クライアントをクローズ"""
        await self._client.aclose()
    
    # =========================================================================
    # Map Matching API
    # =========================================================================
    
    async def map_match(
        self,
        coordinates: list[tuple[float, float]],
        profile: str = "cycling",
    ) -> tuple[GeoJSONLineString, list[VoiceInstruction], float, float]:
        """
        座標列を道路ネットワークにマッチング
        
        Map Matching API を呼び出し、以下を取得:
        1. スナップされたジオメトリ（LineString）
        2. 音声ナビゲーション指示
        3. 正確な距離（メートル）
        4. 所要時間（秒）
        
        API仕様:
        - coordinates: 最大100座標まで
        - steps=true: 詳細な経路ステップを取得
        - voice_instructions=true: 音声指示を取得
        - language=ja: 日本語で音声指示
        
        参照: https://docs.mapbox.com/api/navigation/map-matching/
        「steps: Whether to return steps and turn-by-turn instructions」
        「voice_instructions: Whether to return SSML marked-up text for voice guidance」
        
        Args:
            coordinates: 座標リスト [(経度, 緯度), ...]
            profile: プロファイル ("cycling" / "walking" / "driving")
        
        Returns:
            tuple of:
                - GeoJSONLineString: マッチングされたジオメトリ
                - list[VoiceInstruction]: 音声指示リスト
                - float: 距離（メートル）
                - float: 所要時間（秒）
        
        Raises:
            httpx.HTTPStatusError: API呼び出しエラー
            ValueError: マッチング失敗
        
        使用例:
            geometry, instructions, distance, duration = await client.map_match(
                coordinates=[
                    (135.7588, 34.9858),  # 京都駅
                    (135.7593, 35.0038),  # 四条烏丸
                    (135.7482, 35.0142),  # 二条城
                ],
                profile="cycling"
            )
        """
        # 座標数チェック（API制限: 最大100座標）
        if len(coordinates) > 100:
            # ダウンサンプリング
            step = len(coordinates) // 100 + 1
            coordinates = coordinates[::step]
            # 終点は必ず含める
            if coordinates[-1] != coordinates[-1]:
                coordinates.append(coordinates[-1])
        
        # 座標を文字列に変換: "lon,lat;lon,lat;..."
        coords_str = ";".join(f"{lon},{lat}" for lon, lat in coordinates)
        
        # APIエンドポイント
        profile_name = PROFILES.get(profile, "cycling")
        url = f"{MAPBOX_API_BASE}{MAP_MATCHING_PATH}/{profile_name}/{coords_str}"
        
        # クエリパラメータ
        # 参照: https://docs.mapbox.com/api/navigation/map-matching/#optional-parameters
        params = {
            "access_token": self._access_token,
            "geometries": "geojson",      # GeoJSON形式で返却
            "overview": "full",           # 全ルートのジオメトリ
            "steps": "true",              # ステップ情報を含める
            "voice_instructions": "true", # 音声指示を含める
            "language": "ja",             # 日本語
            "banner_instructions": "true", # バナー指示も含める
        }
        
        # API呼び出し
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        # レスポンス確認
        # 参照: https://docs.mapbox.com/api/navigation/map-matching/#response-retrieve-a-match
        code = data.get("code")
        if code != "Ok":
            raise ValueError(f"Map Matching failed: {code}")
        
        matchings = data.get("matchings", [])
        if not matchings:
            raise ValueError("No matchings found")
        
        # 最初のマッチング結果を使用
        matching = matchings[0]
        
        # ジオメトリ抽出
        geometry_data = matching.get("geometry", {})
        geometry = GeoJSONLineString(
            coordinates=geometry_data.get("coordinates", [])
        )
        
        # 距離・所要時間
        distance = matching.get("distance", 0)  # メートル
        duration = matching.get("duration", 0)  # 秒
        
        # 音声指示抽出
        voice_instructions = self._extract_voice_instructions(matching)
        
        return geometry, voice_instructions, distance, duration
    
    def _extract_voice_instructions(
        self,
        matching: dict,
    ) -> list[VoiceInstruction]:
        """
        マッチング結果から音声指示を抽出
        
        legs -> steps -> voiceInstructions の構造から抽出。
        
        参照: https://docs.mapbox.com/api/navigation/map-matching/#response-retrieve-a-match
        
        Args:
            matching: マッチング結果
        
        Returns:
            音声指示リスト
        """
        instructions = []
        cumulative_distance = 0
        
        legs = matching.get("legs", [])
        for leg in legs:
            steps = leg.get("steps", [])
            for step in steps:
                # このステップの音声指示
                voice_insts = step.get("voiceInstructions", [])
                for vi in voice_insts:
                    # distanceAlongGeometry: このステップ開始からの距離
                    distance_in_step = vi.get("distanceAlongGeometry", 0)
                    announcement = vi.get("announcement", "")
                    
                    if announcement:
                        instructions.append(VoiceInstruction(
                            distance_along_geometry=cumulative_distance + distance_in_step,
                            announcement=announcement,
                        ))
                
                # 累積距離を更新
                step_distance = step.get("distance", 0)
                cumulative_distance += step_distance
        
        return instructions
    
    # =========================================================================
    # ユーティリティ
    # =========================================================================
    
    async def validate_token(self) -> bool:
        """
        アクセストークンの有効性を確認
        
        Returns:
            bool: トークンが有効かどうか
        """
        try:
            # 簡単なリクエストでトークン確認
            test_coords = "135.7588,34.9858;135.7590,34.9860"
            url = f"{MAPBOX_API_BASE}{MAP_MATCHING_PATH}/cycling/{test_coords}"
            params = {"access_token": self._access_token}
            
            response = await self._client.get(url, params=params)
            return response.status_code == 200
        except Exception:
            return False