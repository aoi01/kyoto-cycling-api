"""
app/services/gbfs_client.py

GBFS (General Bikeshare Feed Specification) APIクライアント

シェアサイクル事業者（ドコモ、HELLO CYCLING）のGBFS APIから
ポート情報を取得・キャッシュするクライアント。

公式ドキュメント:
- GBFS仕様: https://gbfs.org/documentation/reference/
- httpx AsyncClient: https://www.python-httpx.org/async/
- asyncio キャッシュ: https://docs.python.org/3/library/functools.html
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import httpx

from app.models.port import Port, PortsData, GBFSStationInfo, GBFSStationStatus


# =============================================================================
# 定数定義
# =============================================================================

# 京都市のバウンディングボックス（この範囲内のポートのみ取得）
KYOTO_BBOX = {
    "min_lat": 34.85,
    "max_lat": 35.15,
    "min_lon": 135.60,
    "max_lon": 135.90,
}

# GBFS APIエンドポイント
# 参照: https://ckan.odpt.org/dataset/c_bikeshare_gbfs-d-nationwide-bikeshare
GBFS_ENDPOINTS = {
    "docomo": {
        "station_information": "https://api-public.odpt.org/api/v4/gbfs/docomo-cycle/station_information.json",
        "station_status": "https://api-public.odpt.org/api/v4/gbfs/docomo-cycle/station_status.json",
    },
    "hellocycling": {
        "station_information": "https://api-public.odpt.org/api/v4/gbfs/hellocycling/station_information.json",
        "station_status": "https://api-public.odpt.org/api/v4/gbfs/hellocycling/station_status.json",
    },
}

# キャッシュTTL
# GBFS仕様: 「station_status は5分以内のデータであるべき」
# 参照: https://gbfs.org/documentation/reference/
STATION_INFO_CACHE_TTL = timedelta(hours=24)  # 静的情報は24時間
STATION_STATUS_CACHE_TTL = timedelta(minutes=1)  # 動的情報は1分


# =============================================================================
# キャッシュエントリ
# =============================================================================

class CacheEntry:
    """
    キャッシュエントリ
    
    データと有効期限を保持する。
    
    Attributes:
        data: キャッシュデータ
        expires_at: 有効期限
    """
    def __init__(self, data, ttl: timedelta):
        self.data = data
        self.expires_at = datetime.now() + ttl
    
    def is_valid(self) -> bool:
        """キャッシュが有効かどうか"""
        return datetime.now() < self.expires_at


# =============================================================================
# GBFSクライアント
# =============================================================================

class GBFSClient:
    """
    GBFSクライアント
    
    シェアサイクル事業者のGBFS APIからポート情報を取得。
    コネクションプーリングとキャッシュにより効率的にデータ取得。
    
    設計根拠:
    - httpx.AsyncClient を共有してコネクションプーリング最大化
      参照: https://www.python-httpx.org/async/
      「You can also instantiate an AsyncClient and share it across multiple requests」
    
    - station_information は24時間キャッシュ（ポート位置は不変）
    - station_status は1分キャッシュ（GBFS仕様「5分以内」に準拠）
    
    Attributes:
        _client (httpx.AsyncClient): HTTPクライアント
        _station_info_cache (dict): station_information キャッシュ
        _station_status_cache (dict): station_status キャッシュ
    
    使用例:
        async with GBFSClient() as client:
            await client.initialize()
            ports_data = await client.get_ports(["docomo", "hellocycling"])
    """
    
    def __init__(self):
        """
        初期化
        
        httpx.AsyncClient の設定:
        - timeout: connect=5秒, read=10秒
        - limits: 最大100接続, キープアライブ20接続
        
        参照: https://www.python-httpx.org/advanced/timeouts/
        """
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=10.0),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
            ),
            # HTTPヘッダー
            headers={
                "User-Agent": "KyotoBikeNavi/1.0",
                "Accept": "application/json",
            },
        )
        
        # キャッシュ: {operator: CacheEntry}
        self._station_info_cache: dict[str, CacheEntry] = {}
        self._station_status_cache: dict[str, CacheEntry] = {}
        
        # 京都市内のポート（station_information から抽出）
        self._kyoto_stations: dict[str, dict[str, GBFSStationInfo]] = {}
    
    async def __aenter__(self):
        """async with 文のエントリポイント"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """async with 文の終了処理"""
        await self.close()
    
    async def close(self):
        """
        クライアントをクローズ
        
        FastAPI の lifespan で呼び出す。
        """
        await self._client.aclose()
    
    # =========================================================================
    # 初期化
    # =========================================================================
    
    async def initialize(self):
        """
        初期化処理
        
        起動時に station_information を取得し、
        京都市内のポートを抽出してキャッシュ。
        
        FastAPI の lifespan の startup で呼び出す。
        """
        print("GBFSClient: Initializing...")
        
        for operator in GBFS_ENDPOINTS.keys():
            try:
                await self._load_station_information(operator)
                print(f"  -> {operator}: {len(self._kyoto_stations.get(operator, {}))} stations in Kyoto")
            except Exception as e:
                print(f"  -> {operator}: Failed to load ({e})")
        
        print("GBFSClient: Initialization complete")
    
    async def _load_station_information(self, operator: str):
        """
        station_information を取得してキャッシュ
        
        Args:
            operator: 事業者識別子 ("docomo" / "hellocycling")
        """
        url = GBFS_ENDPOINTS[operator]["station_information"]
        
        response = await self._client.get(url)
        response.raise_for_status()
        
        data = response.json()
        stations = data.get("data", {}).get("stations", [])
        
        # 京都市内のポートのみ抽出
        kyoto_stations = {}
        for station in stations:
            lat = station.get("lat", 0)
            lon = station.get("lon", 0)
            
            if (KYOTO_BBOX["min_lat"] <= lat <= KYOTO_BBOX["max_lat"] and
                KYOTO_BBOX["min_lon"] <= lon <= KYOTO_BBOX["max_lon"]):
                station_id = station["station_id"]
                kyoto_stations[station_id] = GBFSStationInfo(
                    station_id=station_id,
                    name=station.get("name", ""),
                    lat=lat,
                    lon=lon,
                    capacity=station.get("capacity"),
                )
        
        self._kyoto_stations[operator] = kyoto_stations
        self._station_info_cache[operator] = CacheEntry(kyoto_stations, STATION_INFO_CACHE_TTL)
    
    # =========================================================================
    # ポート取得
    # =========================================================================
    
    async def get_ports(
        self,
        operators: list[str],
        near: Optional[tuple[float, float]] = None,
        radius: int = 500,
        min_bikes: int = 1,
        min_docks: int = 1,
    ) -> PortsData:
        """
        ポート一覧を取得
        
        station_information と station_status を JOIN して
        Port モデルのリストを返す。
        
        Args:
            operators: 事業者リスト ["docomo", "hellocycling"]
            near: 中心座標 (経度, 緯度)。指定時は距離でソート
            radius: near からの半径（メートル）
            min_bikes: 最低空き台数
            min_docks: 最低空きドック数
        
        Returns:
            PortsData: ポート一覧データ
        
        使用例:
            # 全ポート取得
            ports = await client.get_ports(["docomo"])
            
            # 特定地点の近くのポートを取得
            ports = await client.get_ports(
                ["docomo", "hellocycling"],
                near=(135.7588, 34.9858),
                radius=1000
            )
        """
        all_ports: list[Port] = []
        last_updated = datetime.now()
        
        for operator in operators:
            if operator not in GBFS_ENDPOINTS:
                continue
            
            try:
                # station_status を取得（キャッシュ確認）
                statuses = await self._get_station_status(operator)
                
                # station_information と JOIN
                stations = self._kyoto_stations.get(operator, {})
                
                for station_id, info in stations.items():
                    status = statuses.get(station_id)
                    if status is None:
                        continue
                    
                    # フィルタリング
                    if status.num_bikes_available < min_bikes:
                        continue
                    if status.num_docks_available < min_docks:
                        continue
                    
                    port = Port(
                        id=f"{operator}_{station_id}",
                        name=info.name,
                        operator=operator,
                        coordinates=[info.lon, info.lat],
                        bikes_available=status.num_bikes_available,
                        docks_available=status.num_docks_available,
                        is_renting=status.is_renting,
                        is_returning=status.is_returning,
                        last_reported=datetime.fromtimestamp(status.last_reported),
                    )
                    all_ports.append(port)
            
            except Exception as e:
                print(f"GBFSClient: Error getting ports for {operator}: {e}")
        
        # near が指定されている場合、距離でフィルタリング＆ソート
        if near is not None:
            all_ports = self._filter_by_distance(all_ports, near, radius)
        
        return PortsData(
            ports=all_ports,
            total_count=len(all_ports),
            last_updated=last_updated,
        )
    
    async def _get_station_status(self, operator: str) -> dict[str, GBFSStationStatus]:
        """
        station_status を取得（キャッシュ付き）
        
        Args:
            operator: 事業者識別子
        
        Returns:
            {station_id: GBFSStationStatus} の辞書
        """
        # キャッシュ確認
        cache = self._station_status_cache.get(operator)
        if cache and cache.is_valid():
            return cache.data
        
        # API呼び出し
        url = GBFS_ENDPOINTS[operator]["station_status"]
        response = await self._client.get(url)
        response.raise_for_status()
        
        data = response.json()
        stations = data.get("data", {}).get("stations", [])
        
        # 京都市内のポートのみ（station_information で抽出済みのもの）
        kyoto_station_ids = set(self._kyoto_stations.get(operator, {}).keys())
        
        statuses = {}
        for station in stations:
            station_id = station.get("station_id")
            if station_id not in kyoto_station_ids:
                continue
            
            statuses[station_id] = GBFSStationStatus(
                station_id=station_id,
                num_bikes_available=station.get("num_bikes_available", 0),
                num_docks_available=station.get("num_docks_available", 0),
                is_renting=station.get("is_renting", True),
                is_returning=station.get("is_returning", True),
                last_reported=station.get("last_reported", 0),
            )
        
        # キャッシュ更新
        self._station_status_cache[operator] = CacheEntry(statuses, STATION_STATUS_CACHE_TTL)
        
        return statuses
    
    # =========================================================================
    # ユーティリティ
    # =========================================================================
    
    def _filter_by_distance(
        self,
        ports: list[Port],
        center: tuple[float, float],
        radius: float,
    ) -> list[Port]:
        """
        中心座標からの距離でフィルタリング＆ソート
        
        Args:
            ports: ポートリスト
            center: 中心座標 (経度, 緯度)
            radius: 半径（メートル）
        
        Returns:
            距離でソートされたポートリスト
        """
        import math
        
        def haversine(lon1, lat1, lon2, lat2) -> float:
            """2点間の距離（メートル）"""
            R = 6_371_000
            phi1 = math.radians(lat1)
            phi2 = math.radians(lat2)
            delta_phi = math.radians(lat2 - lat1)
            delta_lambda = math.radians(lon2 - lon1)
            
            a = (math.sin(delta_phi / 2) ** 2 +
                 math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            
            return R * c
        
        center_lon, center_lat = center
        
        # 距離計算＆フィルタリング
        ports_with_distance = []
        for port in ports:
            dist = haversine(
                center_lon, center_lat,
                port.coordinates[0], port.coordinates[1]
            )
            if dist <= radius:
                ports_with_distance.append((port, dist))
        
        # 距離でソート
        ports_with_distance.sort(key=lambda x: x[1])
        
        return [p for p, _ in ports_with_distance]