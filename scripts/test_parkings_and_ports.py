"""
scripts/test_parkings_and_ports.py

駐輪場とシェアサイクルポートの取得テストスクリプト

実行方法:
    uv run python scripts/test_parkings_and_ports.py

出力:
    - コンソールにテスト結果を表示
    - parkings_and_ports_test.html にMapbox上で可視化
"""
import asyncio
import json
import os
from pathlib import Path

# プロジェクトルートを取得
PROJECT_ROOT = Path(__file__).parent.parent

# .envを読み込む
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")


async def test_parkings():
    """駐輪場データのテスト"""
    print("=" * 60)
    print("1. 駐輪場データのテスト")
    print("=" * 60)

    # app/data/parkings.py から読み込み
    from app.data import PARKINGS

    print(f"\n総駐輪場数: {len(PARKINGS)}")

    # サンプル表示
    print("\n--- サンプルデータ（最初の5件）---")
    for i, parking in enumerate(PARKINGS[:5]):
        print(f"{i+1}. {parking.name}")
        print(f"   ID: {parking.id}")
        print(f"   座標: [{parking.coordinates[0]}, {parking.coordinates[1]}]")
        print(f"   料金: {parking.fee_description}")
        print()

    # 座標の妥当性チェック
    print("--- 座標の妥当性チェック ---")
    invalid_coords = []
    for parking in PARKINGS:
        lon, lat = parking.coordinates[0], parking.coordinates[1]
        # 京都市の範囲: 経度 135.6-135.9, 緯度 34.85-35.15
        if not (135.6 <= lon <= 135.9 and 34.85 <= lat <= 35.15):
            # 緯度経度が逆の可能性をチェック
            if 135.6 <= lat <= 135.9 and 34.85 <= lon <= 35.15:
                invalid_coords.append({
                    "id": parking.id,
                    "name": parking.name,
                    "coords": parking.coordinates,
                    "issue": "緯度経度が逆の可能性"
                })
            else:
                invalid_coords.append({
                    "id": parking.id,
                    "name": parking.name,
                    "coords": parking.coordinates,
                    "issue": "京都市外の座標"
                })

    if invalid_coords:
        print(f"問題のある座標: {len(invalid_coords)}件")
        for item in invalid_coords[:10]:
            print(f"  - {item['name']}: {item['coords']} ({item['issue']})")
    else:
        print("すべての座標が有効です")

    return PARKINGS


async def test_ports():
    """シェアサイクルポートのテスト"""
    print("\n" + "=" * 60)
    print("2. シェアサイクルポート（GBFS）のテスト")
    print("=" * 60)

    from app.services.gbfs_client import GBFSClient

    client = GBFSClient()

    print("\n--- GBFSクライアント初期化 ---")
    await client.initialize()

    # 各事業者のポート数
    print("\n--- 事業者別ポート数 ---")
    for operator in ["docomo", "hellocycling"]:
        ports_data = await client.get_ports([operator])
        print(f"{operator}: {len(ports_data.ports)}件")

    # 全ポート取得
    all_ports = await client.get_ports(["docomo", "hellocycling"])
    print(f"\n全ポート数: {len(all_ports.ports)}")

    # サンプル表示
    print("\n--- サンプルデータ（最初の5件）---")
    for i, port in enumerate(all_ports.ports[:5]):
        print(f"{i+1}. {port.name}")
        print(f"   ID: {port.id}")
        print(f"   事業者: {port.operator}")
        print(f"   座標: [{port.coordinates[0]}, {port.coordinates[1]}]")
        print(f"   空き自転車: {port.bikes_available}")
        print(f"   空きドック: {port.docks_available}")
        print()

    # 空き自転車があるポート
    available_ports = [p for p in all_ports.ports if p.bikes_available > 0]
    print(f"--- 空き自転車があるポート: {len(available_ports)}件 ---")

    # 返却可能なポート
    returnable_ports = [p for p in all_ports.ports if p.docks_available > 0]
    print(f"--- 返却可能なポート: {len(returnable_ports)}件 ---")

    await client.close()

    return all_ports.ports


async def test_nearest_search():
    """最寄り検索のテスト"""
    print("\n" + "=" * 60)
    print("3. 最寄り検索のテスト")
    print("=" * 60)

    from app.services.route_calculator import RouteCalculator, haversine_distance
    from app.data import PARKINGS
    import pickle

    # グラフ読み込み
    graph_path = PROJECT_ROOT / "app" / "data" / "graph" / "kyoto_bike_graph.pkl"
    with open(graph_path, "rb") as f:
        graph = pickle.load(f)

    calculator = RouteCalculator(graph, parkings=PARKINGS)

    # テスト地点
    test_locations = [
        {"name": "京都駅", "coords": (135.7588, 34.9858)},
        {"name": "金閣寺", "coords": (135.7292, 35.0394)},
        {"name": "清水寺", "coords": (135.7850, 34.9949)},
        {"name": "二条城", "coords": (135.7482, 35.0142)},
    ]

    print("\n--- 各地点の最寄り駐輪場 ---")
    results = []
    for loc in test_locations:
        parking = calculator._find_nearest_parking(loc["coords"], max_distance=1000)
        if parking:
            dist = haversine_distance(
                loc["coords"][0], loc["coords"][1],
                parking.coordinates[0], parking.coordinates[1]
            )
            print(f"{loc['name']}:")
            print(f"  -> {parking.name} (距離: {dist:.0f}m)")
            results.append({
                "location": loc,
                "parking": parking,
                "distance": dist
            })
        else:
            print(f"{loc['name']}: 1km以内に駐輪場なし")
            results.append({
                "location": loc,
                "parking": None,
                "distance": None
            })

    return results


def generate_visualization_html(parkings, ports, mapbox_token):
    """駐輪場とポートを地図上に可視化するHTMLを生成"""

    parkings_data = [
        {
            "id": p.id,
            "name": p.name,
            "coordinates": p.coordinates,
            "fee": p.fee_description
        }
        for p in parkings
    ]

    ports_data = [
        {
            "id": p.id,
            "name": p.name,
            "operator": p.operator,
            "coordinates": p.coordinates,
            "bikes": p.bikes_available,
            "docks": p.docks_available
        }
        for p in ports
    ]

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>駐輪場・シェアサイクルポート確認</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://api.mapbox.com/mapbox-gl-js/v3.0.1/mapbox-gl.js"></script>
    <link href="https://api.mapbox.com/mapbox-gl-js/v3.0.1/mapbox-gl.css" rel="stylesheet">
    <style>
        body {{ margin: 0; padding: 0; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
        #controls {{
            position: absolute;
            top: 10px;
            left: 10px;
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 14px;
            max-width: 300px;
        }}
        #controls h2 {{
            margin: 0 0 15px 0;
            font-size: 16px;
        }}
        .checkbox-group {{
            margin-bottom: 10px;
        }}
        .checkbox-group label {{
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
            margin-bottom: 5px;
        }}
        .stats {{
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #ddd;
            font-size: 12px;
            color: #666;
        }}
        .legend {{
            margin-top: 10px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 5px;
            font-size: 12px;
        }}
        .legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="controls">
        <h2>データ確認</h2>
        <div class="checkbox-group">
            <label>
                <input type="checkbox" id="showParkings" checked>
                駐輪場を表示
            </label>
            <label>
                <input type="checkbox" id="showDocomo" checked>
                docomo ポートを表示
            </label>
            <label>
                <input type="checkbox" id="showHellocycling" checked>
                HELLO CYCLING ポートを表示
            </label>
        </div>
        <div class="legend">
            <div class="legend-item">
                <div class="legend-dot" style="background:#3498db;"></div>
                <span>駐輪場</span>
            </div>
            <div class="legend-item">
                <div class="legend-dot" style="background:#e74c3c;"></div>
                <span>docomo バイクシェア</span>
            </div>
            <div class="legend-item">
                <div class="legend-dot" style="background:#2ecc71;"></div>
                <span>HELLO CYCLING</span>
            </div>
        </div>
        <div class="stats">
            <div>駐輪場: <span id="parkingCount">{len(parkings_data)}</span>件</div>
            <div>docomo: <span id="docomoCount">-</span>件</div>
            <div>HELLO CYCLING: <span id="helloCount">-</span>件</div>
        </div>
    </div>

    <script>
        mapboxgl.accessToken = '{mapbox_token}';

        const map = new mapboxgl.Map({{
            container: 'map',
            style: 'mapbox://styles/mapbox/streets-v12',
            center: [135.7588, 35.0116],
            zoom: 12
        }});

        const parkings = {json.dumps(parkings_data, ensure_ascii=False)};
        const ports = {json.dumps(ports_data, ensure_ascii=False)};

        // 事業者別にカウント
        const docomoPorts = ports.filter(p => p.operator === 'docomo');
        const helloPorts = ports.filter(p => p.operator === 'hellocycling');
        document.getElementById('docomoCount').textContent = docomoPorts.length;
        document.getElementById('helloCount').textContent = helloPorts.length;

        // マーカー配列
        let parkingMarkers = [];
        let docomoMarkers = [];
        let helloMarkers = [];

        map.on('load', () => {{
            // 駐輪場マーカー
            parkings.forEach(p => {{
                const marker = new mapboxgl.Marker({{ color: '#3498db', scale: 0.7 }})
                    .setLngLat(p.coordinates)
                    .setPopup(new mapboxgl.Popup().setHTML(
                        `<b>${{p.name}}</b><br>
                         <small>ID: ${{p.id}}</small><br>
                         <small>料金: ${{p.fee}}</small>`
                    ))
                    .addTo(map);
                parkingMarkers.push(marker);
            }});

            // docomoポートマーカー
            docomoPorts.forEach(p => {{
                const marker = new mapboxgl.Marker({{ color: '#e74c3c', scale: 0.6 }})
                    .setLngLat(p.coordinates)
                    .setPopup(new mapboxgl.Popup().setHTML(
                        `<b>${{p.name}}</b><br>
                         <small>docomo バイクシェア</small><br>
                         <small>空き自転車: ${{p.bikes}}</small><br>
                         <small>空きドック: ${{p.docks}}</small>`
                    ))
                    .addTo(map);
                docomoMarkers.push(marker);
            }});

            // HELLO CYCLINGポートマーカー
            helloPorts.forEach(p => {{
                const marker = new mapboxgl.Marker({{ color: '#2ecc71', scale: 0.6 }})
                    .setLngLat(p.coordinates)
                    .setPopup(new mapboxgl.Popup().setHTML(
                        `<b>${{p.name}}</b><br>
                         <small>HELLO CYCLING</small><br>
                         <small>空き自転車: ${{p.bikes}}</small><br>
                         <small>空きドック: ${{p.docks}}</small>`
                    ))
                    .addTo(map);
                helloMarkers.push(marker);
            }});
        }});

        // チェックボックスでの表示切り替え
        document.getElementById('showParkings').addEventListener('change', (e) => {{
            parkingMarkers.forEach(m => {{
                m.getElement().style.display = e.target.checked ? 'block' : 'none';
            }});
        }});

        document.getElementById('showDocomo').addEventListener('change', (e) => {{
            docomoMarkers.forEach(m => {{
                m.getElement().style.display = e.target.checked ? 'block' : 'none';
            }});
        }});

        document.getElementById('showHellocycling').addEventListener('change', (e) => {{
            helloMarkers.forEach(m => {{
                m.getElement().style.display = e.target.checked ? 'block' : 'none';
            }});
        }});
    </script>
</body>
</html>'''

    return html


async def main():
    """メイン処理"""
    print("駐輪場・シェアサイクルポート取得テスト")
    print("=" * 60)

    # 1. 駐輪場テスト
    parkings = await test_parkings()

    # 2. シェアサイクルポートテスト
    ports = await test_ports()

    # 3. 最寄り検索テスト
    await test_nearest_search()

    # 4. HTML生成
    print("\n" + "=" * 60)
    print("4. 可視化HTML生成")
    print("=" * 60)

    mapbox_token = os.getenv("MAPBOX_ACCESS_TOKEN", "")
    if not mapbox_token:
        print("Warning: MAPBOX_ACCESS_TOKEN not set")
        mapbox_token = "YOUR_TOKEN_HERE"

    html = generate_visualization_html(parkings, ports, mapbox_token)

    output_path = PROJECT_ROOT / "parkings_and_ports_test.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nHTML生成完了: {output_path}")
    print("ブラウザで開いて、駐輪場とポートの位置を確認してください。")

    # サマリー
    print("\n" + "=" * 60)
    print("テストサマリー")
    print("=" * 60)
    print(f"駐輪場: {len(parkings)}件")
    print(f"シェアサイクルポート: {len(ports)}件")
    print(f"  - docomo: {len([p for p in ports if p.operator == 'docomo'])}件")
    print(f"  - HELLO CYCLING: {len([p for p in ports if p.operator == 'hellocycling'])}件")


if __name__ == "__main__":
    asyncio.run(main())
