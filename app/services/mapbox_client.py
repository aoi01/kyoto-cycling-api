"""
app/services/mapbox_client.py

Mapbox API クライアント

トークン検証用の簡易クライアント。
音声案内は VoiceInstructionGenerator で自前実装。

公式ドキュメント:
- httpx AsyncClient: https://www.python-httpx.org/async/
"""
import httpx


# =============================================================================
# 定数定義
# =============================================================================

# Mapbox API エンドポイント
MAPBOX_API_BASE = "https://api.mapbox.com"

# Map Matching API パス（トークン検証用）
MAP_MATCHING_PATH = "/matching/v5/mapbox"

# プロファイル（移動手段）
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

    トークン検証のみを提供。音声案内は VoiceInstructionGenerator で実装。

    Attributes:
        _client (httpx.AsyncClient): HTTPクライアント
        _access_token (str): Mapbox アクセストークン
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
