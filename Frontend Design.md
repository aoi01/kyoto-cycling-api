# フロントエンド設計書: 京都自転車安全ルートナビ

## 1. 技術スタック

| カテゴリ | 技術 | 用途 |
|---------|------|------|
| Framework | React (Vite) + TypeScript | SPA構築 |
| Styling | Tailwind CSS | ユーティリティファーストCSS |
| UI Components | shadcn/ui | Radix UIベースのコンポーネント |
| Map Library | Mapbox GL JS (react-map-gl) | 地図表示・操作 |
| State Management | Zustand | 軽量かつ高速な状態管理 |
| Animation | Framer Motion | ボトムシートのアニメーション |
| Icons | Lucide React | アイコン |
| API Client | Axios | HTTP通信 |

---

## 2. ディレクトリ構成

```
src/
├── assets/                     # アイコン、画像、地図用カスタムマーカー
│   └── markers/                # カスタムマーカー画像
├── components/
│   ├── layout/
│   │   ├── Header.tsx          # 画面上部ヘッダー（カテゴリフィルター）
│   │   └── MainLayout.tsx      # メインレイアウト
│   ├── map/
│   │   ├── MapContainer.tsx    # Mapbox本体とカメラ制御
│   │   ├── SpotMarkers.tsx     # 観光地ピンの描画（spots.ts利用）
│   │   ├── RouteLayer.tsx      # APIから取得したルートの描画
│   │   ├── PortMarkers.tsx     # シェアサイクルポートの描画
│   │   └── UserLocationMarker.tsx # ユーザー現在地マーカー
│   ├── features/
│   │   ├── search/
│   │   │   ├── SearchForm.tsx      # 出発地・目的地・モード設定
│   │   │   ├── LocationInput.tsx   # 場所入力（テキスト＋Geocoding）
│   │   │   └── ModeSelector.tsx    # 移動モード選択
│   │   ├── route/
│   │   │   ├── RouteSummary.tsx    # 距離・時間・安全スコアの表示
│   │   │   ├── RouteDetails.tsx    # ルート詳細（セグメント一覧）
│   │   │   └── ParkingInfo.tsx     # 駐輪場情報表示
│   │   ├── navigation/
│   │   │   ├── VoiceNavigation.tsx # 音声ナビゲーション指示表示
│   │   │   └── NavigationPanel.tsx # ナビゲーションパネル
│   │   └── filter/
│   │       ├── CategoryFilter.tsx  # 観光地カテゴリフィルター（横スクロール）
│   │       └── OperatorFilter.tsx  # シェアサイクル事業者フィルター
│   ├── ui/                     # shadcn/ui コンポーネント
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── checkbox.tsx
│   │   ├── dialog.tsx
│   │   ├── drawer.tsx          # ボトムシート用
│   │   ├── input.tsx
│   │   ├── label.tsx
│   │   ├── scroll-area.tsx     # 横スクロールエリア
│   │   ├── select.tsx
│   │   ├── slider.tsx          # 安全度スライダー
│   │   ├── toast.tsx
│   │   ├── toaster.tsx
│   │   └── toggle-group.tsx    # モード切替
│   └── shared/
│       ├── BottomSheet.tsx     # Drawer拡張ボトムシート
│       └── ErrorBoundary.tsx   # エラーバウンダリ
├── data/
│   └── spots.ts                # 観光地静的データ（フロントエンド管理）
├── hooks/
│   ├── useMapbox.ts            # Mapboxのインスタンス操作
│   ├── useRoute.ts             # /api/route 呼び出し用カスタムフック
│   ├── usePorts.ts             # /api/ports 呼び出し用カスタムフック
│   ├── useGeolocation.ts       # 現在地取得・追跡
│   └── useToast.ts             # トースト通知
├── lib/
│   └── utils.ts                # shadcn/ui用ユーティリティ（cn関数）
├── store/
│   └── useStore.ts             # 検索条件、ルート結果、UI状態のグローバル管理
├── types/
│   ├── api.ts                  # APIレスポンスモデル定義
│   └── spots.ts                # 観光地データ型定義
└── utils/
    ├── coordinates.ts          # 座標変換、バリデーション
    └── mapbox-api.ts           # Geocoding API呼び出し
```

---

## 3. 型定義（types/api.ts）

### 3.1 共通レスポンス

```typescript
// 統一APIレスポンス形式
interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: ErrorDetail;
}

interface ErrorDetail {
  code: string;
  message: string;
}
```

### 3.2 ルート関連

```typescript
// 移動モード
type TransportMode = 'my-cycle' | 'share-cycle';

// セグメント種別
type SegmentType = 'walk' | 'bicycle';

// 地点種別
type PointType = 'origin' | 'destination' | 'parking' | 'port';

// GeoJSON LineString
interface GeoJSONLineString {
  type: 'LineString';
  coordinates: [number, number][];  // [経度, 緯度][]
}

// ルート上の地点
interface RoutePoint {
  type: PointType;
  coordinates: [number, number];  // [経度, 緯度]
  name: string;
  id?: string;              // 駐輪場/ポートID
  feeDescription?: string;  // 駐輪場の料金説明
}

// 音声ナビゲーション指示
interface VoiceInstruction {
  distanceAlongGeometry: number;  // ルート開始点からの距離（メートル）
  announcement: string;           // 音声案内テキスト
}

// ルートジオメトリ
interface RouteGeometry {
  geometry: GeoJSONLineString;
  distance: number;       // メートル
  duration: number;       // 秒
  safetyScore?: number;   // 0-10（自転車区間のみ）
}

// ルートセグメント（区間）
interface RouteSegment {
  type: SegmentType;
  from: RoutePoint;               // 出発地点（※JSONキーは "from"）
  to: RoutePoint;                 // 到着地点
  route: RouteGeometry;
  voiceInstructions: VoiceInstruction[];
}

// ルートサマリー
interface RouteSummary {
  totalDistance: number;       // 総距離（メートル）
  totalDuration: number;       // 総所要時間（秒）
  bicycleDistance: number;     // 自転車区間の距離（メートル）
  walkDistance: number;        // 徒歩区間の距離（メートル）
  averageSafetyScore?: number; // 平均安全スコア（0-10）
}

// ルート検索レスポンス
interface RouteData {
  segments: RouteSegment[];
  summary: RouteSummary;
}
```

### 3.3 シェアサイクルポート関連

```typescript
// 事業者
type Operator = 'docomo' | 'hellocycling';

// シェアサイクルポート
interface Port {
  id: string;
  name: string;
  operator: Operator;
  coordinates: [number, number];  // [経度, 緯度]
  bikesAvailable: number;
  docksAvailable: number;
  isRenting: boolean;
  isReturning: boolean;
  lastReported: string;  // ISO 8601形式
}

// ポート一覧レスポンス
interface PortsData {
  ports: Port[];
  totalCount: number;
  lastUpdated: string;  // ISO 8601形式
}
```

---

## 4. 状態管理（store/useStore.ts）

```typescript
interface SearchParams {
  origin: string;                    // "経度,緯度" または地名
  originCoords?: [number, number];   // 解決済み座標
  destination: string;               // "経度,緯度" または地名
  destinationCoords?: [number, number];
  mode: TransportMode;
  safety: number;                    // 1-10
  needParking: boolean;              // my-cycle時のみ有効
  operators: Operator[];             // share-cycle時のみ有効
}

interface AppState {
  // 検索パラメータ
  searchParams: SearchParams;

  // 結果データ
  routeData: RouteData | null;
  portsData: PortsData | null;

  // ローディング状態
  isSearching: boolean;
  isLoadingPorts: boolean;

  // エラー
  error: ErrorDetail | null;

  // UI状態
  bottomSheetLevel: 1 | 2 | 3;
  selectedSpotId: string | null;

  // 位置追跡（音声ナビ用）
  userLocation: [number, number] | null;
  distanceAlongRoute: number;  // 現在のルート上の距離

  // アクション
  setSearchParams: (params: Partial<SearchParams>) => void;
  setRoute: (data: RouteData) => void;
  setPorts: (data: PortsData) => void;
  setError: (error: ErrorDetail | null) => void;
  setUserLocation: (coords: [number, number]) => void;
  clearRoute: () => void;
}
```

---

## 5. 画面構成とインタラクション
メイン画面（地図）

背景: Mapbox（京都全域を表示）。

観光地ピン: spots.ts のデータを読み込み、カテゴリ（神社、仏閣、ごはん等）に応じたアイコンで表示。

ヘッダー（フィルタ）: 画面上部に横スクロール可能な「カテゴリボタン」を配置。

ボトムシート（初期状態）: 「ここへ行く」などのアクション用。タップで展開。

### 5.1 地図背景（MapContainer）

- Mapbox GL JS を使用し、京都全域を表示
- APIから返却される `GeoJSONLineString` を Source と Layer を用いて地図上に描画
- 初期表示: 京都市中心（135.7588, 35.0116）、ズームレベル 12

### 5.2 観光地ピン（SpotMarkers）

- `spots.ts` のデータを元に、カテゴリに応じたアイコンを表示
- ピンをタップすると、その地点を「目的地」としてセットするポップアップを表示
- カテゴリフィルターと連動

### 5.3 ボトムシート（BottomSheet）

| レベル | 高さ | 表示内容 |
|--------|------|----------|
| Level 1（最小） | 80px | ルート検索後のサマリー（所要時間・距離） |
| Level 2（標準） | 40% | 検索フォーム（出発地、目的地、モード選択） |
| Level 3（全画面） | 90% | 音声ナビ指示リスト（voiceInstructions）の詳細表示 |

Framer Motion の `drag` 機能でスワイプ操作を実現。

### 5.4 ポートマーカー（PortMarkers）

シェアサイクルモード時、ポートを地図上に表示:

```tsx
<Marker longitude={port.coordinates[0]} latitude={port.coordinates[1]}>
  <div className={`port-marker ${port.operator}`}>
    <span className="bikes-count">{port.bikesAvailable}</span>
  </div>
</Marker>
```

---

## 6. ルート検索ロジック（useRoute hook）

### 6.1 APIリクエストパラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|-----|-----|------|
| `origin` | string | ✓ | 出発地 "経度,緯度" |
| `destination` | string | ✓ | 目的地 "経度,緯度" |
| `mode` | string | ✓ | "my-cycle" / "share-cycle" |
| `safety` | int | ✓ | 1-10 |
| `needParking` | bool | - | 駐輪場案内が必要か（デフォルト: true） |
| `operators` | string | - | 事業者（カンマ区切り、share-cycle時に使用） |

### 6.2 モード別UI切り替え

#### my-cycle モード
- 「駐輪場案内」のチェックボックスを表示
- `needParking=true` でリクエスト → 駐輪場経由ルート（2セグメント）
- `needParking=false` でリクエスト → 直接ルート（1セグメント）

#### share-cycle モード
- 「事業者選択（docomo / hellocycling）」のチップスを表示
- `operators` パラメータとして送信
- 3セグメント構成: 徒歩 → 自転車 → 徒歩

### 6.3 セグメント構成

| ユースケース | セグメント数 | 構成 |
|-------------|-------------|------|
| UC-1: 駐輪場経由 | 2 | bicycle → walk |
| UC-2: 直接ルート | 1 | bicycle |
| UC-3: シェアサイクル | 3 | walk → bicycle → walk |

#### UC-3 セグメントの詳細

```
segments[0]:
  type: "walk"
  from.type: "origin"      → to.type: "port" (borrow_port)

segments[1]:
  type: "bicycle"
  from.type: "port"        → to.type: "port" (return_port)

segments[2]:
  type: "walk"
  from.type: "port"        → to.type: "destination"
```

### 6.4 安全度設定

スライダー（1〜5）の値を `safety` パラメータにバインド:

| 値 | 説明 | ルート特性 |
|----|------|-----------|
| 1 | 最短距離重視 | 幹線道路も使用 |
| 5 | 安全最優先 | 可能な限り安全道を使用 |

### 6.5 座標取得

テキスト入力フィールドからMapbox Geocoding APIを使用して座標を解決:

```typescript
// utils/mapbox-api.ts
async function geocode(query: string): Promise<[number, number] | null> {
  const response = await fetch(
    `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(query)}.json?` +
    `access_token=${MAPBOX_TOKEN}&` +
    `bbox=135.60,34.85,135.90,35.15&` +  // 京都市バウンディングボックス
    `language=ja`
  );
  const data = await response.json();
  if (data.features?.length > 0) {
    return data.features[0].center;  // [経度, 緯度]
  }
  return null;
}
```

---

## 7. 音声ナビゲーション（VoiceNavigation）

### 7.1 位置追跡による音声案内

ユーザーの現在位置を追跡し、`distanceAlongGeometry` に近づいたら該当する音声指示を再生/表示:

```typescript
// hooks/useGeolocation.ts
function useGeolocation() {
  const [position, setPosition] = useState<[number, number] | null>(null);

  useEffect(() => {
    const watchId = navigator.geolocation.watchPosition(
      (pos) => setPosition([pos.coords.longitude, pos.coords.latitude]),
      (error) => console.error(error),
      { enableHighAccuracy: true, maximumAge: 1000 }
    );
    return () => navigator.geolocation.clearWatch(watchId);
  }, []);

  return position;
}
```

### 7.2 音声指示の表示ロジック

```typescript
// 現在位置からルート上の距離を計算
const currentDistance = calculateDistanceAlongRoute(userLocation, routeGeometry);

// 次の指示を特定
const nextInstruction = voiceInstructions.find(
  inst => inst.distanceAlongGeometry > currentDistance - 50  // 50m手前から表示
);

// 音声再生（Web Speech API）
if (nextInstruction && shouldAnnounce(nextInstruction)) {
  const utterance = new SpeechSynthesisUtterance(nextInstruction.announcement);
  utterance.lang = 'ja-JP';
  speechSynthesis.speak(utterance);
}
```

---

## 8. ルート表示のスタイリング（RouteLayer）

### 8.1 セグメント種別によるスタイル

| セグメント | 線のスタイル | 色 |
|-----------|-------------|-----|
| bicycle（高安全） | 実線（太め） | 緑 `#34C759` |
| bicycle（中安全） | 実線（太め） | 青 `#007AFF` |
| bicycle（低安全） | 実線（太め） | 橙 `#FF9500` |
| walk | 点線（dasharray） | グレー `#8E8E93` |

### 8.2 安全スコアによる色分け

```typescript
function getRouteColor(safetyScore: number | undefined): string {
  if (safetyScore === undefined) return '#8E8E93';  // 徒歩
  if (safetyScore >= 7) return '#34C759';  // 高安全
  if (safetyScore >= 4) return '#007AFF';  // 中安全
  return '#FF9500';  // 低安全
}
```

### 8.3 Mapbox Layer設定

```tsx
<Layer
  id={`route-segment-${index}`}
  type="line"
  paint={{
    'line-color': getRouteColor(segment.route.safetyScore),
    'line-width': segment.type === 'bicycle' ? 6 : 4,
    'line-opacity': 0.8,
    'line-dasharray': segment.type === 'walk' ? [2, 2] : [1, 0],
  }}
/>
```

---

## 9. ポート取得（usePorts hook）

### 9.1 APIリクエストパラメータ

| パラメータ | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|-----|-----------|------|
| `operators` | string | ✓ | - | 事業者（カンマ区切り） |
| `near` | string | - | - | 中心座標 "経度,緯度" |
| `radius` | int | - | 500 | 半径（メートル） |
| `minBikes` | int | - | 1 | 最低空き台数 |
| `minDocks` | int | - | 1 | 最低空きドック数 |

### 9.2 推奨設定

```typescript
// 現在地周辺のポートを取得
const fetchPorts = async (userLocation: [number, number]) => {
  const response = await axios.get('/api/ports', {
    params: {
      operators: 'docomo,hellocycling',
      near: `${userLocation[0]},${userLocation[1]}`,
      radius: 1000,  // 1km圏内
      minBikes: 1,
    }
  });
  return response.data;
};
```

---

## 10. エラーハンドリング

### 10.1 エラーコード一覧

| コード | 説明 | UI表示 |
|--------|------|--------|
| `INVALID_COORDINATES` | 座標形式が不正 | "座標の形式が正しくありません" |
| `OUT_OF_SERVICE_AREA` | 京都市外の座標 | "京都市外はサービス対象外です" |
| `NO_ROUTE_FOUND` | ルートが見つからない | "ルートが見つかりませんでした" |
| `NO_PARKING_FOUND` | 駐輪場が見つからない | "目的地周辺に駐輪場がありません" |
| `NO_PORT_AVAILABLE` | 利用可能なポートがない | "空き自転車のあるポートが見つかりません" |
| `MAPBOX_API_ERROR` | Mapbox APIエラー | "地図サービスに接続できません" |
| `GBFS_API_ERROR` | GBFS APIエラー | "シェアサイクル情報を取得できません" |

### 10.2 トースト通知

```tsx
// components/shared/Toast.tsx
function Toast({ error, onDismiss }: { error: ErrorDetail; onDismiss: () => void }) {
  const message = ERROR_MESSAGES[error.code] || error.message;

  return (
    <motion.div
      initial={{ opacity: 0, y: 50 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 50 }}
      className="fixed bottom-24 left-4 right-4 bg-red-500 text-white p-4 rounded-lg"
    >
      <p>{message}</p>
      <button onClick={onDismiss}>閉じる</button>
    </motion.div>
  );
}
```

---

## 11. 実装のポイント

### 11.1 モバイル最適化

- 地図操作を妨げないよう、ボトムシートはスワイプで高さを変えられる設計
- Framer Motion の `drag` 機能を利用
- タッチターゲットは最低44x44px

### 11.2 リアルタイム空き状況

- シェアサイクルモード時、`/api/ports` を呼び出し
- ポートマーカー上に「貸出可能台数」を数字で表示
- 30秒ごとに自動更新（ポーリング）

### 11.3 駐輪場情報の表示

UC-1（駐輪場経由）で返される駐輪場情報をボトムシートに表示:

```tsx
<div className="parking-info">
  <h3>{segment.to.name}</h3>
  {segment.to.feeDescription && (
    <p className="fee">{segment.to.feeDescription}</p>
  )}
</div>
```

### 11.4 パフォーマンス考慮

- ルート座標はAPIで簡略化済み（Douglas-Peucker）
- 地図のリレンダリングを最小化（useMemo活用）
- ポートデータはキャッシュ（Zustandのpersist middleware）

---

## 12. API連携まとめ

### 12.1 エンドポイント

| エンドポイント | メソッド | 用途 |
|---------------|---------|------|
| `/api/route` | GET | ルート検索 |
| `/api/ports` | GET | シェアサイクルポート取得 |
| `/health` | GET | ヘルスチェック |

### 12.2 バックエンドURL設定

```typescript
// .env
VITE_API_BASE_URL=http://localhost:8000

// utils/api.ts
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 10000,
});
```

---

## 付録A: 観光地データ構造（spots.ts）

```typescript
interface Spot {
  id: string;
  name: string;
  nameEn: string;
  coordinates: [number, number];
  category: 'temple' | 'shrine' | 'garden' | 'museum' | 'landmark';
  description?: string;
  imageUrl?: string;
}

const SPOTS: Spot[] = [
  {
    id: 'kinkakuji',
    name: '金閣寺',
    nameEn: 'Kinkaku-ji',
    coordinates: [135.7292, 35.0394],
    category: 'temple',
  },
  // ...
];
```

---

## 付録B: 環境変数

| 変数名 | 説明 | 例 |
|--------|------|-----|
| `VITE_API_BASE_URL` | バックエンドAPIのURL | `http://localhost:8000` |
| `VITE_MAPBOX_TOKEN` | Mapboxアクセストークン | `pk.eyJ1...` |

---

## 付録C: プロジェクトセットアップコマンド

### C.1 Vite + React プロジェクト作成

```bash
# プロジェクト作成
npm create vite@latest kyoto-cycling-frontend -- --template react-ts
cd kyoto-cycling-frontend

# 依存パッケージインストール
npm install

# 追加パッケージ
npm install react-map-gl mapbox-gl zustand axios framer-motion lucide-react
npm install -D @types/mapbox-gl tailwindcss postcss autoprefixer
```

### C.2 Tailwind CSS 初期化

```bash
npx tailwindcss init -p
```

### C.3 shadcn/ui 初期化

```bash
npx shadcn@latest init
```

プロンプトで以下を選択:
- Style: Default
- Base color: Slate
- CSS variables: Yes

### C.4 shadcn/ui コンポーネント追加

```bash
npx shadcn@latest add button card checkbox dialog drawer input label scroll-area select slider toast toggle-group
```

### C.5 ディレクトリ構造作成（Windows PowerShell）

```powershell
# ディレクトリ作成
mkdir -Force src\assets\markers
mkdir -Force src\components\layout
mkdir -Force src\components\map
mkdir -Force src\components\features\search
mkdir -Force src\components\features\route
mkdir -Force src\components\features\navigation
mkdir -Force src\components\features\filter
mkdir -Force src\components\shared
mkdir -Force src\data
mkdir -Force src\hooks
mkdir -Force src\lib
mkdir -Force src\store
mkdir -Force src\types
mkdir -Force src\utils
```

### C.6 ファイル作成（Windows PowerShell）

```powershell
# layout
New-Item -ItemType File -Force src\components\layout\Header.tsx
New-Item -ItemType File -Force src\components\layout\MainLayout.tsx

# map
New-Item -ItemType File -Force src\components\map\MapContainer.tsx
New-Item -ItemType File -Force src\components\map\SpotMarkers.tsx
New-Item -ItemType File -Force src\components\map\RouteLayer.tsx
New-Item -ItemType File -Force src\components\map\PortMarkers.tsx
New-Item -ItemType File -Force src\components\map\UserLocationMarker.tsx

# features/search
New-Item -ItemType File -Force src\components\features\search\SearchForm.tsx
New-Item -ItemType File -Force src\components\features\search\LocationInput.tsx
New-Item -ItemType File -Force src\components\features\search\ModeSelector.tsx

# features/route
New-Item -ItemType File -Force src\components\features\route\RouteSummary.tsx
New-Item -ItemType File -Force src\components\features\route\RouteDetails.tsx
New-Item -ItemType File -Force src\components\features\route\ParkingInfo.tsx

# features/navigation
New-Item -ItemType File -Force src\components\features\navigation\VoiceNavigation.tsx
New-Item -ItemType File -Force src\components\features\navigation\NavigationPanel.tsx

# features/filter
New-Item -ItemType File -Force src\components\features\filter\CategoryFilter.tsx
New-Item -ItemType File -Force src\components\features\filter\OperatorFilter.tsx

# shared
New-Item -ItemType File -Force src\components\shared\BottomSheet.tsx
New-Item -ItemType File -Force src\components\shared\ErrorBoundary.tsx

# data
New-Item -ItemType File -Force src\data\spots.ts

# hooks
New-Item -ItemType File -Force src\hooks\useMapbox.ts
New-Item -ItemType File -Force src\hooks\useRoute.ts
New-Item -ItemType File -Force src\hooks\usePorts.ts
New-Item -ItemType File -Force src\hooks\useGeolocation.ts
New-Item -ItemType File -Force src\hooks\useToast.ts

# lib (shadcn/ui initで自動作成される場合あり)
New-Item -ItemType File -Force src\lib\utils.ts

# store
New-Item -ItemType File -Force src\store\useStore.ts

# types
New-Item -ItemType File -Force src\types\api.ts
New-Item -ItemType File -Force src\types\spots.ts

# utils
New-Item -ItemType File -Force src\utils\coordinates.ts
New-Item -ItemType File -Force src\utils\mapbox-api.ts

# 環境変数ファイル
New-Item -ItemType File -Force .env.local
```

### C.7 ディレクトリ構造作成（macOS/Linux bash）

```bash
# ディレクトリ作成
mkdir -p src/assets/markers
mkdir -p src/components/layout
mkdir -p src/components/map
mkdir -p src/components/features/search
mkdir -p src/components/features/route
mkdir -p src/components/features/navigation
mkdir -p src/components/features/filter
mkdir -p src/components/shared
mkdir -p src/data
mkdir -p src/hooks
mkdir -p src/lib
mkdir -p src/store
mkdir -p src/types
mkdir -p src/utils
```

### C.8 ファイル作成（macOS/Linux bash）

```bash
# layout
touch src/components/layout/Header.tsx
touch src/components/layout/MainLayout.tsx

# map
touch src/components/map/MapContainer.tsx
touch src/components/map/SpotMarkers.tsx
touch src/components/map/RouteLayer.tsx
touch src/components/map/PortMarkers.tsx
touch src/components/map/UserLocationMarker.tsx

# features/search
touch src/components/features/search/SearchForm.tsx
touch src/components/features/search/LocationInput.tsx
touch src/components/features/search/ModeSelector.tsx

# features/route
touch src/components/features/route/RouteSummary.tsx
touch src/components/features/route/RouteDetails.tsx
touch src/components/features/route/ParkingInfo.tsx

# features/navigation
touch src/components/features/navigation/VoiceNavigation.tsx
touch src/components/features/navigation/NavigationPanel.tsx

# features/filter
touch src/components/features/filter/CategoryFilter.tsx
touch src/components/features/filter/OperatorFilter.tsx

# shared
touch src/components/shared/BottomSheet.tsx
touch src/components/shared/ErrorBoundary.tsx

# data
touch src/data/spots.ts

# hooks
touch src/hooks/useMapbox.ts
touch src/hooks/useRoute.ts
touch src/hooks/usePorts.ts
touch src/hooks/useGeolocation.ts
touch src/hooks/useToast.ts

# lib
touch src/lib/utils.ts

# store
touch src/store/useStore.ts

# types
touch src/types/api.ts
touch src/types/spots.ts

# utils
touch src/utils/coordinates.ts
touch src/utils/mapbox-api.ts

# 環境変数ファイル
touch .env.local
```

### C.9 .env.local の設定

```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_MAPBOX_TOKEN=your_mapbox_access_token_here
```

### C.10 全コマンド一括実行（Windows PowerShell）

```powershell
# === プロジェクトセットアップ ===
npm create vite@latest kyoto-cycling-frontend -- --template react-ts
cd kyoto-cycling-frontend
npm install
npm install react-map-gl mapbox-gl zustand axios framer-motion lucide-react
npm install -D @types/mapbox-gl tailwindcss postcss autoprefixer
npx tailwindcss init -p
npx shadcn@latest init
npx shadcn@latest add button card checkbox dialog drawer input label scroll-area select slider toast toggle-group

# === ディレクトリ作成 ===
mkdir -Force src\assets\markers
mkdir -Force src\components\layout
mkdir -Force src\components\map
mkdir -Force src\components\features\search
mkdir -Force src\components\features\route
mkdir -Force src\components\features\navigation
mkdir -Force src\components\features\filter
mkdir -Force src\components\shared
mkdir -Force src\data
mkdir -Force src\hooks
mkdir -Force src\lib
mkdir -Force src\store
mkdir -Force src\types
mkdir -Force src\utils

# === ファイル作成 ===
@(
  "src\components\layout\Header.tsx",
  "src\components\layout\MainLayout.tsx",
  "src\components\map\MapContainer.tsx",
  "src\components\map\SpotMarkers.tsx",
  "src\components\map\RouteLayer.tsx",
  "src\components\map\PortMarkers.tsx",
  "src\components\map\UserLocationMarker.tsx",
  "src\components\features\search\SearchForm.tsx",
  "src\components\features\search\LocationInput.tsx",
  "src\components\features\search\ModeSelector.tsx",
  "src\components\features\route\RouteSummary.tsx",
  "src\components\features\route\RouteDetails.tsx",
  "src\components\features\route\ParkingInfo.tsx",
  "src\components\features\navigation\VoiceNavigation.tsx",
  "src\components\features\navigation\NavigationPanel.tsx",
  "src\components\features\filter\CategoryFilter.tsx",
  "src\components\features\filter\OperatorFilter.tsx",
  "src\components\shared\BottomSheet.tsx",
  "src\components\shared\ErrorBoundary.tsx",
  "src\data\spots.ts",
  "src\hooks\useMapbox.ts",
  "src\hooks\useRoute.ts",
  "src\hooks\usePorts.ts",
  "src\hooks\useGeolocation.ts",
  "src\hooks\useToast.ts",
  "src\lib\utils.ts",
  "src\store\useStore.ts",
  "src\types\api.ts",
  "src\types\spots.ts",
  "src\utils\coordinates.ts",
  "src\utils\mapbox-api.ts",
  ".env.local"
) | ForEach-Object { New-Item -ItemType File -Force $_ }

Write-Host "セットアップ完了！" -ForegroundColor Green
```
