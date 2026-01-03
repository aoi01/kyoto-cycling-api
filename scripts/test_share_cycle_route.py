"""
scripts/test_share_cycle_route.py

京都駅 → 金閣寺 のシェアサイクルルートをテストし、
HTMLファイルで可視化するスクリプト

実行方法:
    uv run python scripts/test_share_cycle_route.py

出力:
    share_cycle_route_test.html
"""
import asyncio
import json
import os
import pickle
from pathlib import Path

# プロジェクトルートを取得
PROJECT_ROOT = Path(__file__).parent.parent

# .envを読み込む
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")


async def test_share_cycle_route():
    """シェアサイクルルートのテスト"""
    from app.services.route_calculator import RouteCalculator
    from app.services.gbfs_client import GBFSClient
    from app.data import PARKINGS

    print("=" * 70)
    print("京都駅 → 金閣寺 シェアサイクルルートテスト")
    print("=" * 70)

    # テスト地点
    origin = (135.7588, 34.9858)       # 京都駅
    destination = (135.7292, 35.0394)  # 金閣寺

    print(f"\n出発地: 京都駅 {origin}")
    print(f"目的地: 金閣寺 {destination}")

    # グラフ読み込み
    graph_path = PROJECT_ROOT / "app" / "data" / "graph" / "kyoto_bike_graph.pkl"
    print(f"\nグラフ読み込み中: {graph_path}")
    with open(graph_path, "rb") as f:
        graph = pickle.load(f)
    print(f"  -> ノード: {len(graph.nodes):,}, エッジ: {len(graph.edges):,}")

    # RouteCalculator初期化
    calculator = RouteCalculator(graph, parkings=PARKINGS)

    # GBFSクライアント初期化
    print("\nGBFSクライアント初期化中...")
    gbfs_client = GBFSClient()
    await gbfs_client.initialize()

    # docomoポートのみ取得
    print("\ndocomoポート取得中...")
    ports_data = await gbfs_client.get_ports(["docomo"])
    ports = ports_data.ports
    print(f"  -> 取得ポート数: {len(ports)}")

    # シェアサイクルルート計算
    print("\nシェアサイクルルート計算中...")
    safety = 7  # 安全性重視

    result = calculator.calculate_share_cycle_route(
        origin=origin,
        destination=destination,
        safety=safety,
        ports=ports,
    )

    # 結果表示
    print("\n" + "=" * 70)
    print("計算結果")
    print("=" * 70)

    # レンタルポート情報（APIでは borrow_port）
    rental_port = result.get("borrow_port")
    if rental_port:
        print(f"\n【レンタルポート（自転車を借りる場所）】")
        print(f"  名前: {rental_port.name}")
        print(f"  ID: {rental_port.id}")
        print(f"  座標: [{rental_port.coordinates[0]}, {rental_port.coordinates[1]}]")
        print(f"  空き自転車: {rental_port.bikes_available}台")
        print(f"  空きドック: {rental_port.docks_available}")

    # 返却ポート情報
    return_port = result.get("return_port")
    if return_port:
        print(f"\n【返却ポート（自転車を返す場所）】")
        print(f"  名前: {return_port.name}")
        print(f"  ID: {return_port.id}")
        print(f"  座標: [{return_port.coordinates[0]}, {return_port.coordinates[1]}]")
        print(f"  空き自転車: {return_port.bikes_available}台")
        print(f"  空きドック: {return_port.docks_available}")

    # セグメント情報を構築
    walk_to_port_dist = result.get("walk_to_port", 0)
    bicycle_route = result.get("bicycle_route")
    walk_from_port_dist = result.get("walk_from_port", 0)

    print(f"\n【ルートセグメント】")

    # 徒歩区間1: 出発地→レンタルポート
    print(f"  1. 徒歩（出発地→レンタルポート）")
    print(f"     距離: {walk_to_port_dist:.0f}m")

    # 自転車区間
    if bicycle_route:
        print(f"  2. 自転車（レンタルポート→返却ポート）")
        print(f"     距離: {bicycle_route.distance:.0f}m, 座標数: {len(bicycle_route.coordinates)}")
    else:
        print(f"  2. 自転車区間: 計算失敗")

    # 徒歩区間2: 返却ポート→目的地
    print(f"  3. 徒歩（返却ポート→目的地）")
    print(f"     距離: {walk_from_port_dist:.0f}m")

    total_distance = result.get("total_distance", 0)
    print(f"\n【総距離】{total_distance:.0f}m ({total_distance/1000:.2f}km)")

    # セグメントデータを構築（HTML用）
    segments = []

    # 徒歩区間1の座標（直線）
    if rental_port:
        segments.append({
            "type": "walk_to_port",
            "coordinates": [list(origin), rental_port.coordinates],
            "distance": walk_to_port_dist,
        })

    # 自転車区間
    if bicycle_route and bicycle_route.coordinates:
        segments.append({
            "type": "cycle",
            "coordinates": bicycle_route.coordinates,
            "distance": bicycle_route.distance,
        })

    # 徒歩区間2の座標（直線）
    if return_port:
        segments.append({
            "type": "walk_from_port",
            "coordinates": [return_port.coordinates, list(destination)],
            "distance": walk_from_port_dist,
        })

    await gbfs_client.close()

    return {
        "origin": origin,
        "destination": destination,
        "rental_port": rental_port,
        "return_port": return_port,
        "segments": segments,
        "all_docomo_ports": ports,
    }


def generate_html(data: dict, mapbox_token: str) -> str:
    """
    シェアサイクルルートをMapbox上に可視化するHTMLを生成
    """
    origin = data["origin"]
    destination = data["destination"]
    rental_port = data["rental_port"]
    return_port = data["return_port"]
    segments = data["segments"]
    all_ports = data["all_docomo_ports"]

    # セグメントデータをJSON化
    segments_json = []
    for seg in segments:
        segments_json.append({
            "type": seg.get("type"),
            "coordinates": seg.get("coordinates", []),
            "distance": seg.get("distance", 0),
        })

    # 全docomoポートをJSON化（空き自転車があるもののみ）
    available_ports = [
        {
            "id": p.id,
            "name": p.name,
            "coordinates": p.coordinates,
            "bikes": p.bikes_available,
            "docks": p.docks_available,
        }
        for p in all_ports
        if p.bikes_available > 0
    ]

    # レンタル・返却ポート情報
    rental_info = {
        "id": rental_port.id,
        "name": rental_port.name,
        "coordinates": rental_port.coordinates,
        "bikes": rental_port.bikes_available,
        "docks": rental_port.docks_available,
    } if rental_port else None

    return_info = {
        "id": return_port.id,
        "name": return_port.name,
        "coordinates": return_port.coordinates,
        "bikes": return_port.bikes_available,
        "docks": return_port.docks_available,
    } if return_port else None

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>シェアサイクルルートテスト: 京都駅 → 金閣寺</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://api.mapbox.com/mapbox-gl-js/v3.0.1/mapbox-gl.js"></script>
    <link href="https://api.mapbox.com/mapbox-gl-js/v3.0.1/mapbox-gl.css" rel="stylesheet">
    <style>
        body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
        #info {{
            position: absolute;
            top: 10px;
            left: 10px;
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            max-width: 380px;
            max-height: 85vh;
            overflow-y: auto;
            font-size: 14px;
        }}
        #info h2 {{
            margin: 0 0 15px 0;
            font-size: 18px;
            color: #333;
            border-bottom: 2px solid #e74c3c;
            padding-bottom: 10px;
        }}
        .section {{
            margin-bottom: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
        }}
        .section h3 {{
            margin: 0 0 10px 0;
            font-size: 14px;
            color: #555;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .section h3 .icon {{
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 12px;
        }}
        .port-info {{
            background: white;
            padding: 10px;
            border-radius: 6px;
            margin-top: 8px;
        }}
        .port-info .name {{
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
        }}
        .port-info .detail {{
            font-size: 12px;
            color: #666;
        }}
        .availability {{
            display: flex;
            gap: 15px;
            margin-top: 8px;
        }}
        .availability .item {{
            display: flex;
            align-items: center;
            gap: 5px;
            font-size: 12px;
        }}
        .availability .bikes {{ color: #27ae60; }}
        .availability .docks {{ color: #3498db; }}
        .segment {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }}
        .segment:last-child {{ border-bottom: none; }}
        .segment .num {{
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 11px;
            font-weight: bold;
        }}
        .segment .walk {{ background: #9b59b6; }}
        .segment .cycle {{ background: #e74c3c; }}
        .segment .info {{
            flex: 1;
        }}
        .segment .type {{ font-size: 12px; color: #888; }}
        .segment .distance {{ font-weight: bold; color: #333; }}
        .legend {{
            margin-top: 20px;
            padding-top: 15px;
            border-top: 1px solid #ddd;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
            font-size: 12px;
        }}
        .legend-line {{
            width: 30px;
            height: 4px;
            border-radius: 2px;
        }}
        .legend-marker {{
            width: 16px;
            height: 16px;
            border-radius: 50%;
        }}
        .checkbox-group {{
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #ddd;
        }}
        .checkbox-group label {{
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
            font-size: 13px;
            margin-bottom: 5px;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="info">
        <h2>🚲 シェアサイクルルート</h2>
        <p style="margin: 0 0 15px 0; color: #666; font-size: 13px;">
            京都駅 → 金閣寺（docomo バイクシェア）
        </p>

        <div class="section">
            <h3>
                <span class="icon" style="background: #27ae60;">借</span>
                レンタルポート
            </h3>
            <div class="port-info">
                <div class="name" id="rental-name">-</div>
                <div class="detail" id="rental-detail">-</div>
                <div class="availability">
                    <div class="item bikes">🚲 空き自転車: <span id="rental-bikes">-</span>台</div>
                    <div class="item docks">🅿️ 空きドック: <span id="rental-docks">-</span></div>
                </div>
            </div>
        </div>

        <div class="section">
            <h3>
                <span class="icon" style="background: #c0392b;">返</span>
                返却ポート
            </h3>
            <div class="port-info">
                <div class="name" id="return-name">-</div>
                <div class="detail" id="return-detail">-</div>
                <div class="availability">
                    <div class="item bikes">🚲 空き自転車: <span id="return-bikes">-</span>台</div>
                    <div class="item docks">🅿️ 空きドック: <span id="return-docks">-</span></div>
                </div>
            </div>
        </div>

        <div class="section">
            <h3>📍 ルート詳細</h3>
            <div id="segments"></div>
        </div>

        <div class="legend">
            <div class="legend-item">
                <div class="legend-line" style="background: #9b59b6;"></div>
                <span>徒歩区間</span>
            </div>
            <div class="legend-item">
                <div class="legend-line" style="background: #e74c3c;"></div>
                <span>自転車区間</span>
            </div>
            <div class="legend-item">
                <div class="legend-marker" style="background: #27ae60;"></div>
                <span>出発地（京都駅）</span>
            </div>
            <div class="legend-item">
                <div class="legend-marker" style="background: #c0392b;"></div>
                <span>目的地（金閣寺）</span>
            </div>
            <div class="legend-item">
                <div class="legend-marker" style="background: #e74c3c; opacity: 0.5;"></div>
                <span>その他のdocomoポート（空き自転車あり）</span>
            </div>
        </div>

        <div class="checkbox-group">
            <label>
                <input type="checkbox" id="showAllPorts" checked>
                他のdocomoポートを表示
            </label>
        </div>
    </div>

    <script>
        mapboxgl.accessToken = '{mapbox_token}';

        const map = new mapboxgl.Map({{
            container: 'map',
            style: 'mapbox://styles/mapbox/streets-v12',
            center: [135.74, 35.01],
            zoom: 13
        }});

        // データ
        const origin = {json.dumps(list(origin))};
        const destination = {json.dumps(list(destination))};
        const segments = {json.dumps(segments_json)};
        const rentalPort = {json.dumps(rental_info)};
        const returnPort = {json.dumps(return_info)};
        const availablePorts = {json.dumps(available_ports)};

        // ポート情報を表示
        if (rentalPort) {{
            document.getElementById('rental-name').textContent = rentalPort.name;
            document.getElementById('rental-detail').textContent = `ID: ${{rentalPort.id}}`;
            document.getElementById('rental-bikes').textContent = rentalPort.bikes;
            document.getElementById('rental-docks').textContent = rentalPort.docks;
        }}
        if (returnPort) {{
            document.getElementById('return-name').textContent = returnPort.name;
            document.getElementById('return-detail').textContent = `ID: ${{returnPort.id}}`;
            document.getElementById('return-bikes').textContent = returnPort.bikes;
            document.getElementById('return-docks').textContent = returnPort.docks;
        }}

        // セグメント情報を表示
        const segmentsDiv = document.getElementById('segments');
        let totalDistance = 0;
        segments.forEach((seg, i) => {{
            totalDistance += seg.distance;
            const typeLabel = {{
                'walk_to_port': '徒歩（駅→ポート）',
                'cycle': '自転車',
                'walk_from_port': '徒歩（ポート→金閣寺）'
            }}[seg.type] || seg.type;

            const isWalk = seg.type.includes('walk');
            segmentsDiv.innerHTML += `
                <div class="segment">
                    <div class="num ${{isWalk ? 'walk' : 'cycle'}}">${{i + 1}}</div>
                    <div class="info">
                        <div class="type">${{typeLabel}}</div>
                        <div class="distance">${{(seg.distance / 1000).toFixed(2)}} km</div>
                    </div>
                </div>
            `;
        }});
        segmentsDiv.innerHTML += `
            <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #ddd; font-weight: bold;">
                総距離: ${{(totalDistance / 1000).toFixed(2)}} km
            </div>
        `;

        // 他ポートのマーカー配列
        let otherPortMarkers = [];

        map.on('load', () => {{
            const bounds = new mapboxgl.LngLatBounds();

            // セグメントを描画
            const colors = {{
                'walk_to_port': '#9b59b6',
                'cycle': '#e74c3c',
                'walk_from_port': '#9b59b6'
            }};

            segments.forEach((seg, i) => {{
                if (seg.coordinates && seg.coordinates.length > 0) {{
                    const color = colors[seg.type] || '#888';
                    const isWalk = seg.type.includes('walk');

                    map.addSource(`segment-${{i}}`, {{
                        type: 'geojson',
                        data: {{
                            type: 'Feature',
                            geometry: {{
                                type: 'LineString',
                                coordinates: seg.coordinates
                            }}
                        }}
                    }});

                    map.addLayer({{
                        id: `segment-${{i}}`,
                        type: 'line',
                        source: `segment-${{i}}`,
                        layout: {{
                            'line-join': 'round',
                            'line-cap': 'round'
                        }},
                        paint: {{
                            'line-color': color,
                            'line-width': isWalk ? 4 : 6,
                            'line-opacity': 0.8,
                            'line-dasharray': isWalk ? [2, 2] : [1]
                        }}
                    }});

                    seg.coordinates.forEach(coord => bounds.extend(coord));
                }}
            }});

            // 出発地マーカー
            new mapboxgl.Marker({{ color: '#27ae60', scale: 1.2 }})
                .setLngLat(origin)
                .setPopup(new mapboxgl.Popup().setHTML('<b>出発地</b><br>京都駅'))
                .addTo(map);

            // 目的地マーカー
            new mapboxgl.Marker({{ color: '#c0392b', scale: 1.2 }})
                .setLngLat(destination)
                .setPopup(new mapboxgl.Popup().setHTML('<b>目的地</b><br>金閣寺'))
                .addTo(map);

            // レンタルポートマーカー
            if (rentalPort) {{
                const el = document.createElement('div');
                el.innerHTML = '借';
                el.style.cssText = 'background:#27ae60;color:white;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:bold;border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.3);';

                new mapboxgl.Marker({{ element: el }})
                    .setLngLat(rentalPort.coordinates)
                    .setPopup(new mapboxgl.Popup().setHTML(
                        `<b>レンタルポート</b><br>
                         ${{rentalPort.name}}<br>
                         <small>空き自転車: ${{rentalPort.bikes}}台</small>`
                    ))
                    .addTo(map);
            }}

            // 返却ポートマーカー
            if (returnPort) {{
                const el = document.createElement('div');
                el.innerHTML = '返';
                el.style.cssText = 'background:#c0392b;color:white;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:bold;border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.3);';

                new mapboxgl.Marker({{ element: el }})
                    .setLngLat(returnPort.coordinates)
                    .setPopup(new mapboxgl.Popup().setHTML(
                        `<b>返却ポート</b><br>
                         ${{returnPort.name}}<br>
                         <small>空きドック: ${{returnPort.docks}}</small>`
                    ))
                    .addTo(map);
            }}

            // 他のdocomoポート（選択されたポート以外）
            const selectedIds = new Set([rentalPort?.id, returnPort?.id].filter(Boolean));
            availablePorts.forEach(port => {{
                if (!selectedIds.has(port.id)) {{
                    const marker = new mapboxgl.Marker({{ color: '#e74c3c', scale: 0.5 }})
                        .setLngLat(port.coordinates)
                        .setPopup(new mapboxgl.Popup().setHTML(
                            `<b>${{port.name}}</b><br>
                             <small>空き自転車: ${{port.bikes}}台</small><br>
                             <small>空きドック: ${{port.docks}}</small>`
                        ))
                        .addTo(map);
                    otherPortMarkers.push(marker);
                }}
            }});

            // 地図をルート全体が見えるようにフィット
            bounds.extend(origin);
            bounds.extend(destination);
            map.fitBounds(bounds, {{ padding: 80 }});
        }});

        // 他ポートの表示切り替え
        document.getElementById('showAllPorts').addEventListener('change', (e) => {{
            otherPortMarkers.forEach(m => {{
                m.getElement().style.display = e.target.checked ? 'block' : 'none';
            }});
        }});
    </script>
</body>
</html>'''

    return html


async def main():
    """メイン処理"""
    # ルート計算
    result = await test_share_cycle_route()

    # HTML生成
    print("\n" + "=" * 70)
    print("HTML生成")
    print("=" * 70)

    mapbox_token = os.getenv("MAPBOX_ACCESS_TOKEN", "")
    if not mapbox_token:
        print("Warning: MAPBOX_ACCESS_TOKEN not set")
        mapbox_token = "YOUR_TOKEN_HERE"

    html = generate_html(result, mapbox_token)

    output_path = PROJECT_ROOT / "share_cycle_route_test.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nHTML生成完了: {output_path}")
    print("ブラウザで開いて、シェアサイクルルートを確認してください。")


if __name__ == "__main__":
    asyncio.run(main())
