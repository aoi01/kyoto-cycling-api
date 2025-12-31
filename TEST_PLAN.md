# 京都自転車安全ルートナビ API テスト計画書

## 概要

このドキュメントでは、京都自転車安全ルートナビAPIの包括的なテスト計画を定義します。

## テスト対象エンドポイント

| エンドポイント | メソッド | 説明 |
|---------------|---------|------|
| `/api/route` | GET | ルート検索（UC-1, UC-2, UC-3） |
| `/api/ports` | GET | シェアサイクルポート一覧 |
| `/health` | GET | ヘルスチェック |
| `/debug/graph-info` | GET | グラフ情報取得 |
| `/debug/test-route` | GET | テストルート計算 |
| `/debug/weight-factors` | GET | 重み係数表示 |

---

## テスト環境構築

### 1. 開発依存関係のインストール

```bash
# uvを使用する場合
uv sync --dev

# pipを使用する場合
pip install -e ".[dev]"
```

### 2. 必要なパッケージ（pyproject.tomlに定義済み）

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",           # テストフレームワーク
    "pytest-asyncio>=0.24.0",  # 非同期テスト対応
    "pytest-cov>=6.0.0",       # カバレッジ計測
    "respx>=0.21.0",           # httpxモック
    "ruff>=0.8.0",             # リンター
    "mypy>=1.13.0",            # 型チェック
]
```

### 3. pytest設定（pyproject.toml）

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### 4. テストディレクトリ構造

```
tests/
├── __init__.py
├── conftest.py              # 共通フィクスチャ
├── test_health.py           # ヘルスチェックテスト
├── test_route_api.py        # ルートAPIテスト
├── test_ports_api.py        # ポートAPIテスト
├── test_route_calculator.py # ルート計算ユニットテスト
└── test_models.py           # モデルバリデーションテスト
```

---

## テストケース詳細

### 1. ヘルスチェック (`/health`)

| # | テストケース | 期待結果 |
|---|-------------|---------|
| 1.1 | GET /health | `{"status": "healthy"}` を返す |

---

### 2. ルート検索API (`/api/route`)

#### 2.1 正常系 - UC-2: 直接ルート（自転車）

| # | テストケース | パラメータ | 期待結果 |
|---|-------------|-----------|---------|
| 2.1.1 | 基本的な直接ルート | origin=135.7588,34.9858<br>destination=135.7482,35.0142<br>mode=my-cycle<br>safety=5<br>needParking=false | 成功レスポンス、segments配列に1つのsegment |
| 2.1.2 | 安全度最小 | safety=1 | 最短距離重視のルート |
| 2.1.3 | 安全度最大 | safety=10 | 安全道優先のルート |

#### 2.2 正常系 - UC-1: 駐輪場経由ルート

| # | テストケース | パラメータ | 期待結果 |
|---|-------------|-----------|---------|
| 2.2.1 | 駐輪場経由 | mode=my-cycle<br>needParking=true | segments配列に2つのsegment（bicycle + walk） |
| 2.2.2 | 駐輪場情報あり | needParking=true | parking情報がレスポンスに含まれる |

#### 2.3 正常系 - UC-3: シェアサイクル

| # | テストケース | パラメータ | 期待結果 |
|---|-------------|-----------|---------|
| 2.3.1 | シェアサイクル基本 | mode=share-cycle<br>operators=docomo | 成功、3つのsegment（walk→bicycle→walk） |
| 2.3.2 | 複数事業者 | operators=docomo,hellocycling | 両事業者のポートを検索 |

#### 2.4 異常系 - バリデーションエラー

| # | テストケース | パラメータ | 期待結果 |
|---|-------------|-----------|---------|
| 2.4.1 | 無効な座標形式 | origin=invalid | 400 Bad Request または INVALID_ORIGIN |
| 2.4.2 | 範囲外のsafety | safety=0 | バリデーションエラー |
| 2.4.3 | 範囲外のsafety | safety=11 | バリデーションエラー |
| 2.4.4 | 京都市外の座標 | origin=139.7,35.6 | INVALID_ORIGIN または OUT_OF_BOUNDS |
| 2.4.5 | 必須パラメータ不足 | originのみ | バリデーションエラー |
| 2.4.6 | 無効なmode | mode=invalid | バリデーションエラー |

---

### 3. ポートAPI (`/api/ports`)

#### 3.1 正常系

| # | テストケース | パラメータ | 期待結果 |
|---|-------------|-----------|---------|
| 3.1.1 | docomo単一 | operators=docomo | docomoポート一覧 |
| 3.1.2 | 複数事業者 | operators=docomo,hellocycling | 両事業者のポート |
| 3.1.3 | 座標指定 | near=135.7588,34.9858 | 距離順ソート |
| 3.1.4 | 半径フィルタ | near=135.7588,34.9858<br>radius=1000 | 1km以内のポート |
| 3.1.5 | 台数フィルタ | minBikes=3 | 3台以上空きのポート |
| 3.1.6 | ドック数フィルタ | minDocks=2 | 2ドック以上空きのポート |

#### 3.2 異常系

| # | テストケース | パラメータ | 期待結果 |
|---|-------------|-----------|---------|
| 3.2.1 | 無効なnear形式 | near=invalid | INVALID_COORDINATES |
| 3.2.2 | 不正な事業者 | operators=unknown | 空のポートリストまたはエラー |

---

### 4. ルート計算ユニットテスト (`RouteCalculator`)

#### 4.1 最寄りノード検索

| # | テストケース | 入力 | 期待結果 |
|---|-------------|-----|---------|
| 4.1.1 | 京都駅付近 | (135.7588, 34.9858) | 京都駅に近いノードID |
| 4.1.2 | グラフ境界 | グラフ端の座標 | 最も近いノード |

#### 4.2 直接ルート計算

| # | テストケース | 入力 | 期待結果 |
|---|-------------|-----|---------|
| 4.2.1 | 正常ルート | 京都駅→二条城 | RouteResult（distance>0, safety_score 0-10） |
| 4.2.2 | 同一地点 | 同一座標 | 距離0または例外 |

#### 4.3 重み計算

| # | テストケース | 入力 | 期待結果 |
|---|-------------|-----|---------|
| 4.3.1 | safety=1 | 100m, is_safe=True | ~97.0 |
| 4.3.2 | safety=1 | 100m, is_safe=False | ~120.0 |
| 4.3.3 | safety=10 | 100m, is_safe=True | ~70.0 |
| 4.3.4 | safety=10 | 100m, is_safe=False | ~300.0 |

#### 4.4 駐輪場検索

| # | テストケース | 入力 | 期待結果 |
|---|-------------|-----|---------|
| 4.4.1 | 最寄り検索 | 京都駅座標 | 800m以内の駐輪場 |
| 4.4.2 | 範囲外 | 遠い座標 | None |

---

### 5. モデルバリデーションテスト

#### 5.1 Parking モデル

| # | テストケース | 期待結果 |
|---|-------------|---------|
| 5.1.1 | 正常な値 | Parkingインスタンス作成成功 |
| 5.1.2 | 座標が逆順 | バリデーションまたはチェック |

#### 5.2 RouteData モデル

| # | テストケース | 期待結果 |
|---|-------------|---------|
| 5.2.1 | 全フィールド設定 | インスタンス作成成功 |
| 5.2.2 | JSONシリアライズ | camelCase変換 |

---

## テスト実行コマンド

### 基本実行

```bash
# 全テスト実行
uv run pytest

# 詳細出力
uv run pytest -v

# 特定ファイル
uv run pytest tests/test_health.py

# 特定テスト
uv run pytest tests/test_route_api.py::test_direct_route_basic
```

### カバレッジ計測

```bash
# カバレッジ付き実行
uv run pytest --cov=app --cov-report=html

# HTMLレポートは htmlcov/index.html に出力
```

### 並列実行（pytest-xdist使用時）

```bash
uv run pytest -n auto
```

---

## モック戦略

### 1. GBFSClient のモック

外部GBFS APIへのリクエストをモックして、テストの安定性を確保。

```python
@pytest.fixture
def mock_gbfs_client():
    client = MagicMock(spec=GBFSClient)
    client.get_ports.return_value = PortsData(ports=[], total_count=0)
    return client
```

### 2. MapboxClient のモック

Mapbox Map Matching APIをモックして、音声指示のテストを実行。

```python
@pytest.fixture
def mock_mapbox_client():
    client = MagicMock(spec=MapboxClient)
    client.get_voice_instructions.return_value = ([], None)
    return client
```

### 3. respx によるHTTPモック

```python
import respx

@respx.mock
async def test_gbfs_api_call():
    respx.get("https://api.example.com/gbfs").respond(json={"data": []})
    # テスト実行
```

---

## 環境変数（テスト用）

```bash
# テスト実行時は.envファイルまたは環境変数で設定
MAPBOX_ACCESS_TOKEN=test_token_for_testing
GRAPH_PATH=app/data/graph/kyoto_bike_graph.pkl
```

---

## 品質基準

| メトリクス | 目標値 |
|-----------|--------|
| カバレッジ（行） | >= 80% |
| カバレッジ（分岐） | >= 70% |
| 全テスト成功 | 100% |

---

## 次のステップ

1. [x] テスト計画作成（本ドキュメント）
2. [ ] `tests/conftest.py` - 共通フィクスチャ作成
3. [ ] `tests/test_health.py` - ヘルスチェックテスト
4. [ ] `tests/test_route_api.py` - ルートAPIテスト
5. [ ] `tests/test_ports_api.py` - ポートAPIテスト
6. [ ] `tests/test_route_calculator.py` - ユニットテスト
7. [ ] `tests/test_models.py` - モデルテスト
8. [ ] テスト実行・カバレッジ確認
