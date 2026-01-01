# フロントエンド実装計画書

京都自転車安全ルートナビ API を React フロントエンドから使用するための実装ガイドです。

---

## 技術スタック

| レイヤー | 技術 |
|---------|------|
| フロントエンド | React + TypeScript |
| 地図ライブラリ | Mapbox GL JS または React Map GL |
| HTTP クライアント | fetch API または axios |
| 状態管理 | React Query（TanStack Query）推奨 |
| バックエンド | Python FastAPI（本API） |

---

## アーキテクチャ概要

```
┌─────────────────────────────────────────────────────────────┐
│                      React Frontend                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  MapView    │  │  SearchForm │  │  RouteDetails       │  │
│  │  (Mapbox)   │  │             │  │  (距離/時間/安全度) │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│         │                │                    │              │
│         └────────────────┼────────────────────┘              │
│                          │                                   │
│                    ┌─────▼─────┐                             │
│                    │ useRoute  │  (カスタムフック)           │
│                    │ usePorts  │                             │
│                    └─────┬─────┘                             │
└──────────────────────────┼───────────────────────────────────┘
                           │ HTTP
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI Backend                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ /api/route  │  │ /api/ports  │  │ /health             │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## ディレクトリ構成（推奨）

```
frontend/
├── src/
│   ├── api/
│   │   ├── client.ts          # API クライアント設定
│   │   ├── routeApi.ts        # ルートAPI関数
│   │   └── portsApi.ts        # ポートAPI関数
│   ├── components/
│   │   ├── Map/
│   │   │   ├── MapView.tsx    # 地図コンポーネント
│   │   │   ├── RouteLayer.tsx # ルート描画レイヤー
│   │   │   └── PortMarker.tsx # ポートマーカー
│   │   ├── Search/
│   │   │   ├── SearchForm.tsx # 検索フォーム
│   │   │   └── SafetySlider.tsx # 安全度スライダー
│   │   └── Route/
│   │       ├── RouteDetails.tsx   # ルート詳細
│   │       ├── SegmentList.tsx    # セグメント一覧
│   │       └── VoiceNavigation.tsx # 音声ナビ
│   ├── hooks/
│   │   ├── useRoute.ts        # ルート検索フック
│   │   ├── usePorts.ts        # ポート取得フック
│   │   └── useGeolocation.ts  # 位置情報フック
│   ├── types/
│   │   ├── route.ts           # ルート関連の型定義
│   │   └── port.ts            # ポート関連の型定義
│   └── App.tsx
├── package.json
└── .env
```

---

## Step 1: 型定義

### `src/types/route.ts`

```typescript
// 移動モード
export type TransportMode = 'my-cycle' | 'share-cycle';

// セグメント種別
export type SegmentType = 'walk' | 'bicycle';

// 地点種別
export type PointType = 'origin' | 'destination' | 'parking' | 'port';

// 座標
export type Coordinates = [number, number]; // [経度, 緯度]

// 地点
export interface RoutePoint {
  type: PointType;
  coordinates: Coordinates;
  name: string;
  id?: string;
  feeDescription?: string;
}

// GeoJSON LineString
export interface GeoJSONLineString {
  type: 'LineString';
  coordinates: Coordinates[];
}

// 音声指示
export interface VoiceInstruction {
  distanceAlongGeometry: number;
  announcement: string;
}

// ルートジオメトリ
export interface RouteGeometry {
  geometry: GeoJSONLineString;
  distance: number;
  duration: number;
  safetyScore?: number;
}

// ルートセグメント
export interface RouteSegment {
  type: SegmentType;
  from: RoutePoint;
  to: RoutePoint;
  route: RouteGeometry;
  voiceInstructions: VoiceInstruction[];
}

// ルートサマリー
export interface RouteSummary {
  totalDistance: number;
  totalDuration: number;
  bicycleDistance: number;
  walkDistance: number;
  averageSafetyScore?: number;
}

// ルートデータ
export interface RouteData {
  segments: RouteSegment[];
  summary: RouteSummary;
}

// APIレスポンス
export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  error: {
    code: string;
    message: string;
  } | null;
}

// ルート検索パラメータ
export interface RouteSearchParams {
  origin: Coordinates;
  destination: Coordinates;
  mode: TransportMode;
  safety: number;
  needParking?: boolean;
  operators?: string;
}
```

### `src/types/port.ts`

```typescript
import { Coordinates } from './route';

export interface Port {
  id: string;
  name: string;
  operator: string;
  coordinates: Coordinates;
  bikesAvailable: number;
  docksAvailable: number;
  isRenting: boolean;
  isReturning: boolean;
  lastReported: string;
}

export interface PortsData {
  ports: Port[];
  totalCount: number;
  lastUpdated: string;
}

export interface PortsSearchParams {
  operators: string;
  near?: Coordinates;
  radius?: number;
  minBikes?: number;
  minDocks?: number;
}
```

---

## Step 2: API クライアント

### `src/api/client.ts`

```typescript
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function apiRequest<T>(
  endpoint: string,
  params?: Record<string, string | number | boolean>
): Promise<T> {
  const url = new URL(endpoint, API_BASE_URL);

  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        url.searchParams.append(key, String(value));
      }
    });
  }

  const response = await fetch(url.toString(), {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`API Error: ${response.status}`);
  }

  return response.json();
}
```

### `src/api/routeApi.ts`

```typescript
import { apiRequest } from './client';
import { ApiResponse, RouteData, RouteSearchParams, Coordinates } from '../types/route';

/**
 * ルート検索
 */
export async function searchRoute(params: RouteSearchParams): Promise<ApiResponse<RouteData>> {
  const queryParams = {
    origin: `${params.origin[0]},${params.origin[1]}`,
    destination: `${params.destination[0]},${params.destination[1]}`,
    mode: params.mode,
    safety: params.safety,
    needParking: params.needParking ?? false,
    operators: params.operators,
  };

  return apiRequest<ApiResponse<RouteData>>('/api/route', queryParams);
}

/**
 * 座標をパース
 */
export function parseCoordinates(str: string): Coordinates | null {
  const parts = str.split(',');
  if (parts.length !== 2) return null;

  const lon = parseFloat(parts[0]);
  const lat = parseFloat(parts[1]);

  if (isNaN(lon) || isNaN(lat)) return null;
  return [lon, lat];
}

/**
 * 距離をフォーマット
 */
export function formatDistance(meters: number): string {
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(1)}km`;
  }
  return `${Math.round(meters)}m`;
}

/**
 * 所要時間をフォーマット
 */
export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}時間${mins}分`;
  }
  return `${minutes}分`;
}
```

### `src/api/portsApi.ts`

```typescript
import { apiRequest } from './client';
import { ApiResponse, PortsData, PortsSearchParams } from '../types/port';

/**
 * ポート一覧取得
 */
export async function getPorts(params: PortsSearchParams): Promise<ApiResponse<PortsData>> {
  const queryParams: Record<string, string | number> = {
    operators: params.operators,
  };

  if (params.near) {
    queryParams.near = `${params.near[0]},${params.near[1]}`;
  }
  if (params.radius) {
    queryParams.radius = params.radius;
  }
  if (params.minBikes) {
    queryParams.minBikes = params.minBikes;
  }
  if (params.minDocks) {
    queryParams.minDocks = params.minDocks;
  }

  return apiRequest<ApiResponse<PortsData>>('/api/ports', queryParams);
}
```

---

## Step 3: カスタムフック

### `src/hooks/useRoute.ts`

```typescript
import { useState, useCallback } from 'react';
import { searchRoute } from '../api/routeApi';
import { RouteData, RouteSearchParams } from '../types/route';

interface UseRouteResult {
  route: RouteData | null;
  loading: boolean;
  error: string | null;
  search: (params: RouteSearchParams) => Promise<void>;
  clear: () => void;
}

export function useRoute(): UseRouteResult {
  const [route, setRoute] = useState<RouteData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = useCallback(async (params: RouteSearchParams) => {
    setLoading(true);
    setError(null);

    try {
      const response = await searchRoute(params);

      if (response.success && response.data) {
        setRoute(response.data);
      } else {
        setError(response.error?.message || 'ルートが見つかりませんでした');
        setRoute(null);
      }
    } catch (err) {
      setError('通信エラーが発生しました');
      setRoute(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const clear = useCallback(() => {
    setRoute(null);
    setError(null);
  }, []);

  return { route, loading, error, search, clear };
}
```

### `src/hooks/usePorts.ts`

```typescript
import { useState, useCallback } from 'react';
import { getPorts } from '../api/portsApi';
import { Port, PortsSearchParams } from '../types/port';

interface UsePortsResult {
  ports: Port[];
  loading: boolean;
  error: string | null;
  fetch: (params: PortsSearchParams) => Promise<void>;
}

export function usePorts(): UsePortsResult {
  const [ports, setPorts] = useState<Port[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async (params: PortsSearchParams) => {
    setLoading(true);
    setError(null);

    try {
      const response = await getPorts(params);

      if (response.success && response.data) {
        setPorts(response.data.ports);
      } else {
        setError(response.error?.message || 'ポートが見つかりませんでした');
      }
    } catch (err) {
      setError('通信エラーが発生しました');
    } finally {
      setLoading(false);
    }
  }, []);

  return { ports, loading, error, fetch };
}
```

---

## Step 4: コンポーネント実装

### `src/components/Search/SearchForm.tsx`

```typescript
import React, { useState } from 'react';
import { Coordinates, TransportMode, RouteSearchParams } from '../../types/route';

interface SearchFormProps {
  onSearch: (params: RouteSearchParams) => void;
  loading: boolean;
}

export function SearchForm({ onSearch, loading }: SearchFormProps) {
  const [origin, setOrigin] = useState<Coordinates>([135.7588, 34.9858]); // 京都駅
  const [destination, setDestination] = useState<Coordinates>([135.7482, 35.0142]); // 二条城
  const [mode, setMode] = useState<TransportMode>('my-cycle');
  const [safety, setSafety] = useState(5);
  const [needParking, setNeedParking] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch({
      origin,
      destination,
      mode,
      safety,
      needParking: mode === 'my-cycle' ? needParking : undefined,
      operators: mode === 'share-cycle' ? 'docomo,hellocycling' : undefined,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="search-form">
      <div className="form-group">
        <label>出発地</label>
        <input
          type="text"
          value={`${origin[0]},${origin[1]}`}
          onChange={(e) => {
            const [lon, lat] = e.target.value.split(',').map(Number);
            if (!isNaN(lon) && !isNaN(lat)) setOrigin([lon, lat]);
          }}
          placeholder="経度,緯度"
        />
      </div>

      <div className="form-group">
        <label>目的地</label>
        <input
          type="text"
          value={`${destination[0]},${destination[1]}`}
          onChange={(e) => {
            const [lon, lat] = e.target.value.split(',').map(Number);
            if (!isNaN(lon) && !isNaN(lat)) setDestination([lon, lat]);
          }}
          placeholder="経度,緯度"
        />
      </div>

      <div className="form-group">
        <label>移動モード</label>
        <select value={mode} onChange={(e) => setMode(e.target.value as TransportMode)}>
          <option value="my-cycle">自分の自転車</option>
          <option value="share-cycle">シェアサイクル</option>
        </select>
      </div>

      <div className="form-group">
        <label>安全度: {safety}</label>
        <input
          type="range"
          min={1}
          max={10}
          value={safety}
          onChange={(e) => setSafety(Number(e.target.value))}
        />
        <div className="safety-labels">
          <span>最短距離</span>
          <span>安全優先</span>
        </div>
      </div>

      {mode === 'my-cycle' && (
        <div className="form-group">
          <label>
            <input
              type="checkbox"
              checked={needParking}
              onChange={(e) => setNeedParking(e.target.checked)}
            />
            駐輪場を案内する
          </label>
        </div>
      )}

      <button type="submit" disabled={loading}>
        {loading ? '検索中...' : 'ルート検索'}
      </button>
    </form>
  );
}
```

### `src/components/Map/MapView.tsx`

```typescript
import React, { useRef, useEffect } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { RouteData } from '../../types/route';

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN;

interface MapViewProps {
  route: RouteData | null;
  onMapClick?: (coordinates: [number, number]) => void;
}

export function MapView({ route, onMapClick }: MapViewProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);

  // 地図初期化
  useEffect(() => {
    if (!mapContainer.current) return;

    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/streets-v12',
      center: [135.7588, 34.9858], // 京都駅
      zoom: 13,
    });

    map.current.on('click', (e) => {
      if (onMapClick) {
        onMapClick([e.lngLat.lng, e.lngLat.lat]);
      }
    });

    return () => {
      map.current?.remove();
    };
  }, []);

  // ルート描画
  useEffect(() => {
    if (!map.current || !route) return;

    const mapInstance = map.current;

    // 既存のルートレイヤーを削除
    if (mapInstance.getLayer('route-line')) {
      mapInstance.removeLayer('route-line');
    }
    if (mapInstance.getSource('route')) {
      mapInstance.removeSource('route');
    }

    // 全セグメントの座標を結合
    const allCoordinates: [number, number][] = [];
    route.segments.forEach((segment) => {
      allCoordinates.push(...segment.route.geometry.coordinates);
    });

    // ルートソースを追加
    mapInstance.addSource('route', {
      type: 'geojson',
      data: {
        type: 'Feature',
        properties: {},
        geometry: {
          type: 'LineString',
          coordinates: allCoordinates,
        },
      },
    });

    // ルートレイヤーを追加
    mapInstance.addLayer({
      id: 'route-line',
      type: 'line',
      source: 'route',
      layout: {
        'line-join': 'round',
        'line-cap': 'round',
      },
      paint: {
        'line-color': '#3b82f6',
        'line-width': 5,
        'line-opacity': 0.8,
      },
    });

    // ルート全体が見えるようにズーム
    const bounds = new mapboxgl.LngLatBounds();
    allCoordinates.forEach((coord) => bounds.extend(coord));
    mapInstance.fitBounds(bounds, { padding: 50 });

  }, [route]);

  return <div ref={mapContainer} className="map-container" />;
}
```

### `src/components/Route/RouteDetails.tsx`

```typescript
import React from 'react';
import { RouteData } from '../../types/route';
import { formatDistance, formatDuration } from '../../api/routeApi';

interface RouteDetailsProps {
  route: RouteData;
}

export function RouteDetails({ route }: RouteDetailsProps) {
  const { summary, segments } = route;

  return (
    <div className="route-details">
      <h3>ルート情報</h3>

      <div className="summary">
        <div className="summary-item">
          <span className="label">総距離</span>
          <span className="value">{formatDistance(summary.totalDistance)}</span>
        </div>
        <div className="summary-item">
          <span className="label">所要時間</span>
          <span className="value">{formatDuration(summary.totalDuration)}</span>
        </div>
        {summary.averageSafetyScore && (
          <div className="summary-item">
            <span className="label">安全スコア</span>
            <span className="value">{summary.averageSafetyScore.toFixed(1)} / 10</span>
          </div>
        )}
      </div>

      <div className="segments">
        <h4>ルート詳細</h4>
        {segments.map((segment, index) => (
          <div key={index} className={`segment segment-${segment.type}`}>
            <div className="segment-icon">
              {segment.type === 'bicycle' ? '🚲' : '🚶'}
            </div>
            <div className="segment-info">
              <div className="segment-points">
                <span>{segment.from.name}</span>
                <span>→</span>
                <span>{segment.to.name}</span>
              </div>
              <div className="segment-stats">
                <span>{formatDistance(segment.route.distance)}</span>
                <span>{formatDuration(segment.route.duration)}</span>
                {segment.route.safetyScore && (
                  <span>安全度: {segment.route.safetyScore.toFixed(1)}</span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 駐輪場情報（UC-1の場合） */}
      {segments.some(s => s.to.type === 'parking') && (
        <div className="parking-info">
          <h4>駐輪場情報</h4>
          {segments
            .filter(s => s.to.type === 'parking')
            .map((s, i) => (
              <div key={i} className="parking">
                <span className="parking-name">{s.to.name}</span>
                {s.to.feeDescription && (
                  <span className="parking-fee">{s.to.feeDescription}</span>
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
```

---

## Step 5: メインアプリケーション

### `src/App.tsx`

```typescript
import React from 'react';
import { MapView } from './components/Map/MapView';
import { SearchForm } from './components/Search/SearchForm';
import { RouteDetails } from './components/Route/RouteDetails';
import { useRoute } from './hooks/useRoute';
import './App.css';

function App() {
  const { route, loading, error, search, clear } = useRoute();

  return (
    <div className="app">
      <header className="app-header">
        <h1>京都自転車ナビ</h1>
      </header>

      <main className="app-main">
        <aside className="sidebar">
          <SearchForm onSearch={search} loading={loading} />

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          {route && (
            <>
              <RouteDetails route={route} />
              <button onClick={clear} className="clear-button">
                クリア
              </button>
            </>
          )}
        </aside>

        <div className="map-area">
          <MapView route={route} />
        </div>
      </main>
    </div>
  );
}

export default App;
```

---

## Step 6: 環境設定

### `.env`

```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_MAPBOX_ACCESS_TOKEN=pk.eyJ1Ijoi...
```

### `package.json`（主要な依存関係）

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "mapbox-gl": "^3.0.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "typescript": "^5.0.0",
    "vite": "^5.0.0"
  }
}
```

---

## Step 7: CORS設定（バックエンド側）

フロントエンドの開発サーバー（localhost:5173など）からAPIにアクセスするため、バックエンドのCORS設定を確認：

[app/main.py:200-207](app/main.py#L200-L207)

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",      # Vite開発サーバー
        "http://localhost:3000",      # その他
        "https://your-frontend.com",  # 本番環境
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

---

## ユースケース別実装例

### UC-1: 駐輪場経由ルート

```typescript
const result = await searchRoute({
  origin: [135.7588, 34.9858],      // 京都駅
  destination: [135.7482, 35.0142], // 二条城
  mode: 'my-cycle',
  safety: 7,
  needParking: true,  // 駐輪場案内あり
});

// segments[0]: 自転車区間（出発地 → 駐輪場）
// segments[1]: 徒歩区間（駐輪場 → 目的地）
```

### UC-2: 直接ルート

```typescript
const result = await searchRoute({
  origin: [135.7588, 34.9858],
  destination: [135.7482, 35.0142],
  mode: 'my-cycle',
  safety: 5,
  needParking: false,  // 直接目的地へ
});

// segments[0]: 自転車区間（出発地 → 目的地）
```

### UC-3: シェアサイクル

```typescript
const result = await searchRoute({
  origin: [135.7588, 34.9858],
  destination: [135.7482, 35.0142],
  mode: 'share-cycle',
  safety: 5,
  operators: 'docomo,hellocycling',
});

// segments[0]: 徒歩区間（出発地 → 貸出ポート）
// segments[1]: 自転車区間（貸出ポート → 返却ポート）
// segments[2]: 徒歩区間（返却ポート → 目的地）
```

---

## 音声ナビゲーション実装（オプション）

```typescript
import { VoiceInstruction } from '../types/route';

export function useVoiceNavigation(instructions: VoiceInstruction[]) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const synth = window.speechSynthesis;

  const speak = useCallback((text: string) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'ja-JP';
    synth.speak(utterance);
  }, []);

  const checkAndAnnounce = useCallback((distanceFromStart: number) => {
    const instruction = instructions[currentIndex];
    if (!instruction) return;

    // 指示地点に近づいたら音声案内
    if (distanceFromStart >= instruction.distanceAlongGeometry - 50) {
      speak(instruction.announcement);
      setCurrentIndex(prev => prev + 1);
    }
  }, [instructions, currentIndex, speak]);

  return { checkAndAnnounce };
}
```

---

## 開発手順まとめ

1. **環境構築**: Vite + React + TypeScript プロジェクト作成
2. **型定義**: API レスポンスの型を定義
3. **API クライアント**: fetch ラッパーとAPI関数を実装
4. **カスタムフック**: 状態管理ロジックをフックに抽出
5. **コンポーネント**: 検索フォーム、地図、ルート詳細を実装
6. **地図連携**: Mapbox GL JS でルート描画
7. **テスト**: 各ユースケースの動作確認

---

## 参考リンク

- [Mapbox GL JS ドキュメント](https://docs.mapbox.com/mapbox-gl-js/guides/)
- [React Map GL](https://visgl.github.io/react-map-gl/)
- [TanStack Query](https://tanstack.com/query/latest)
- [Vite](https://vitejs.dev/)
