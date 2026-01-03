"""
scripts/visualize_routes.py

複数のルートを計算し、Mapbox上に表示するHTMLを生成するスクリプト

実行方法:
    uv run python scripts/visualize_routes.py

出力:
    routes_visualization.html
"""
import pickle
import json
from pathlib import Path
from shapely.geometry import LineString

# プロジェクトルートを取得
PROJECT_ROOT = Path(__file__).parent.parent


def load_graph():
    """グラフデータを読み込む"""
    graph_path = PROJECT_ROOT / "app" / "data" / "graph" / "kyoto_bike_graph.pkl"
    print(f"Loading graph from {graph_path}...")
    with open(graph_path, "rb") as f:
        graph = pickle.load(f)
    print(f"  -> Loaded: {len(graph.nodes):,} nodes, {len(graph.edges):,} edges")
    return graph


def simplify_coordinates(coordinates: list, tolerance: float = 0.0001) -> list:
    """Douglas-Peuckerで座標を簡略化"""
    if len(coordinates) < 3:
        return coordinates

    line = LineString(coordinates)
    simplified = line.simplify(tolerance, preserve_topology=True)
    return list(simplified.coords)


def calculate_route(graph, origin: tuple, destination: tuple, safety: int = 5):
    """
    A*アルゴリズムでルートを計算

    簡易実装: RouteCalculatorを使わずに直接NetworkXを使用
    """
    import networkx as nx
    import math

    # 最寄りノードを検索
    def find_nearest_node(lon, lat):
        min_dist = float('inf')
        nearest = None
        for node, data in graph.nodes(data=True):
            node_lon = data.get('x', 0)
            node_lat = data.get('y', 0)
            dist = math.sqrt((node_lon - lon)**2 + (node_lat - lat)**2)
            if dist < min_dist:
                min_dist = dist
                nearest = node
        return nearest

    origin_node = find_nearest_node(origin[0], origin[1])
    dest_node = find_nearest_node(destination[0], destination[1])

    if origin_node is None or dest_node is None:
        raise ValueError("Could not find nearest nodes")

    # 重み計算
    def weight_func(u, v, data):
        length = data.get('length', 100)
        is_safe = data.get('is_safe', False)

        if is_safe:
            factor = 1.0 - (safety - 1) * 0.05  # safety=10で0.55
        else:
            factor = 1.0 + (safety - 1) * 0.15  # safety=10で2.35

        return length * factor

    # ヒューリスティック関数
    def heuristic(u, v):
        u_data = graph.nodes[u]
        v_data = graph.nodes[v]
        dx = u_data.get('x', 0) - v_data.get('x', 0)
        dy = u_data.get('y', 0) - v_data.get('y', 0)
        return math.sqrt(dx**2 + dy**2) * 111000  # 度をメートルに概算変換

    # A*で経路探索
    try:
        path = nx.astar_path(graph, origin_node, dest_node, heuristic=heuristic, weight=weight_func)
    except nx.NetworkXNoPath:
        raise ValueError("No path found")

    # 座標を抽出
    coordinates = []
    total_distance = 0

    for i, node in enumerate(path):
        data = graph.nodes[node]
        coordinates.append([data.get('x', 0), data.get('y', 0)])

        if i > 0:
            prev_node = path[i-1]
            # エッジの距離を取得
            edge_data = graph.get_edge_data(prev_node, node)
            if edge_data:
                # MultiDiGraphなので最初のエッジを取得
                first_edge = list(edge_data.values())[0]
                total_distance += first_edge.get('length', 0)

    return {
        'coordinates': coordinates,
        'distance': total_distance,
        'node_count': len(path),
    }


def generate_html(routes: list, mapbox_token: str) -> str:
    """
    ルートをMapbox上に表示するHTMLを生成

    Args:
        routes: ルート情報のリスト
        mapbox_token: Mapboxアクセストークン

    Returns:
        HTML文字列
    """
    # 色のリスト
    colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6']

    # ルートデータをJSON化
    routes_json = json.dumps(routes, ensure_ascii=False)

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>京都自転車ルート可視化</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://api.mapbox.com/mapbox-gl-js/v3.0.1/mapbox-gl.js"></script>
    <link href="https://api.mapbox.com/mapbox-gl-js/v3.0.1/mapbox-gl.css" rel="stylesheet">
    <style>
        body {{ margin: 0; padding: 0; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
        #info {{
            position: absolute;
            top: 10px;
            left: 10px;
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            max-width: 350px;
            max-height: 80vh;
            overflow-y: auto;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 14px;
        }}
        #info h2 {{
            margin: 0 0 15px 0;
            font-size: 18px;
            border-bottom: 2px solid #333;
            padding-bottom: 8px;
        }}
        .route-item {{
            margin-bottom: 15px;
            padding: 10px;
            border-radius: 6px;
            background: #f8f9fa;
        }}
        .route-item h3 {{
            margin: 0 0 8px 0;
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .color-dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
        }}
        .route-item p {{
            margin: 4px 0;
            color: #555;
            font-size: 12px;
        }}
        .stats {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 5px;
            margin-top: 8px;
        }}
        .stat {{
            background: white;
            padding: 5px 8px;
            border-radius: 4px;
            font-size: 11px;
        }}
        .stat-label {{ color: #888; }}
        .stat-value {{ font-weight: bold; color: #333; }}
        .legend {{
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #ddd;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 5px;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="info">
        <h2>京都自転車ルート可視化</h2>
        <div id="routes-list"></div>
        <div class="legend">
            <div class="legend-item">
                <span style="width:20px;height:3px;background:#e74c3c;display:inline-block;"></span>
                <span>元の座標（細かい）</span>
            </div>
            <div class="legend-item">
                <span style="width:20px;height:3px;background:#3498db;display:inline-block;border-style:dashed;"></span>
                <span>簡略化後の座標</span>
            </div>
        </div>
    </div>

    <script>
        mapboxgl.accessToken = '{mapbox_token}';

        const map = new mapboxgl.Map({{
            container: 'map',
            style: 'mapbox://styles/mapbox/streets-v12',
            center: [135.7588, 35.0116],  // 京都市中心
            zoom: 12
        }});

        const routes = {routes_json};
        const colors = {json.dumps(colors)};

        map.on('load', () => {{
            const bounds = new mapboxgl.LngLatBounds();
            const routesList = document.getElementById('routes-list');

            routes.forEach((route, index) => {{
                const color = colors[index % colors.length];
                const simplifiedColor = '#2980b9';

                // 元のルート（実線）
                map.addSource(`route-original-${{index}}`, {{
                    type: 'geojson',
                    data: {{
                        type: 'Feature',
                        geometry: {{
                            type: 'LineString',
                            coordinates: route.original_coordinates
                        }}
                    }}
                }});

                map.addLayer({{
                    id: `route-original-${{index}}`,
                    type: 'line',
                    source: `route-original-${{index}}`,
                    layout: {{
                        'line-join': 'round',
                        'line-cap': 'round'
                    }},
                    paint: {{
                        'line-color': color,
                        'line-width': 4,
                        'line-opacity': 0.7
                    }}
                }});

                // 簡略化後のルート（破線）
                map.addSource(`route-simplified-${{index}}`, {{
                    type: 'geojson',
                    data: {{
                        type: 'Feature',
                        geometry: {{
                            type: 'LineString',
                            coordinates: route.simplified_coordinates
                        }}
                    }}
                }});

                map.addLayer({{
                    id: `route-simplified-${{index}}`,
                    type: 'line',
                    source: `route-simplified-${{index}}`,
                    layout: {{
                        'line-join': 'round',
                        'line-cap': 'round'
                    }},
                    paint: {{
                        'line-color': simplifiedColor,
                        'line-width': 3,
                        'line-dasharray': [2, 2],
                        'line-opacity': 0.9
                    }}
                }});

                // 始点マーカー
                new mapboxgl.Marker({{ color: '#27ae60' }})
                    .setLngLat(route.original_coordinates[0])
                    .setPopup(new mapboxgl.Popup().setHTML(`<b>${{route.name}}</b><br>始点: ${{route.origin_name}}`))
                    .addTo(map);

                // 終点マーカー
                new mapboxgl.Marker({{ color: '#c0392b' }})
                    .setLngLat(route.original_coordinates[route.original_coordinates.length - 1])
                    .setPopup(new mapboxgl.Popup().setHTML(`<b>${{route.name}}</b><br>終点: ${{route.destination_name}}`))
                    .addTo(map);

                // bounds更新
                route.original_coordinates.forEach(coord => bounds.extend(coord));

                // 情報パネル更新
                routesList.innerHTML += `
                    <div class="route-item">
                        <h3>
                            <span class="color-dot" style="background:${{color}}"></span>
                            ${{route.name}}
                        </h3>
                        <p>${{route.origin_name}} → ${{route.destination_name}}</p>
                        <div class="stats">
                            <div class="stat">
                                <div class="stat-label">距離</div>
                                <div class="stat-value">${{(route.distance / 1000).toFixed(2)}} km</div>
                            </div>
                            <div class="stat">
                                <div class="stat-label">元の座標数</div>
                                <div class="stat-value">${{route.original_count}} 点</div>
                            </div>
                            <div class="stat">
                                <div class="stat-label">簡略化後</div>
                                <div class="stat-value">${{route.simplified_count}} 点</div>
                            </div>
                            <div class="stat">
                                <div class="stat-label">削減率</div>
                                <div class="stat-value">${{((1 - route.simplified_count / route.original_count) * 100).toFixed(1)}}%</div>
                            </div>
                        </div>
                    </div>
                `;
            }});

            // 全ルートが見えるようにズーム
            map.fitBounds(bounds, {{ padding: 50 }});
        }});
    </script>
</body>
</html>'''

    return html


def main():
    """メイン処理"""
    import os
    from dotenv import load_dotenv

    # .envを読み込む
    load_dotenv(PROJECT_ROOT / ".env")

    mapbox_token = os.getenv("MAPBOX_ACCESS_TOKEN", "")
    if not mapbox_token:
        print("Warning: MAPBOX_ACCESS_TOKEN not set. Using placeholder.")
        mapbox_token = "YOUR_MAPBOX_TOKEN_HERE"

    # グラフ読み込み
    graph = load_graph()

    # テストルート定義
    test_routes = [
        {
            "name": "ルート1: 京都駅 → 金閣寺",
            "origin": (135.7588, 34.9858),
            "destination": (135.7292, 35.0394),
            "origin_name": "京都駅",
            "destination_name": "金閣寺",
            "safety": 7,
        },
        {
            "name": "ルート2: 京都駅 → 二条城",
            "origin": (135.7588, 34.9858),
            "destination": (135.7482, 35.0142),
            "origin_name": "京都駅",
            "destination_name": "二条城",
            "safety": 5,
        },
        {
            "name": "ルート3: 四条烏丸 → 清水寺",
            "origin": (135.7593, 35.0038),
            "destination": (135.7850, 34.9949),
            "origin_name": "四条烏丸",
            "destination_name": "清水寺",
            "safety": 8,
        },
        {
            "name": "ルート4: 金閣寺 → 銀閣寺",
            "origin": (135.7292, 35.0394),
            "destination": (135.7982, 35.0270),
            "origin_name": "金閣寺",
            "destination_name": "銀閣寺",
            "safety": 6,
        },
    ]

    routes_data = []

    for route_def in test_routes:
        print(f"\nCalculating: {route_def['name']}")

        try:
            result = calculate_route(
                graph,
                route_def["origin"],
                route_def["destination"],
                route_def["safety"]
            )

            original_coords = result["coordinates"]
            simplified_coords = simplify_coordinates(original_coords, tolerance=0.0001)

            print(f"  Distance: {result['distance']:.0f}m")
            print(f"  Coordinates: {len(original_coords)} -> {len(simplified_coords)} (simplified)")
            print(f"  Reduction: {(1 - len(simplified_coords)/len(original_coords))*100:.1f}%")

            routes_data.append({
                "name": route_def["name"],
                "origin_name": route_def["origin_name"],
                "destination_name": route_def["destination_name"],
                "distance": result["distance"],
                "original_coordinates": original_coords,
                "simplified_coordinates": list(simplified_coords),
                "original_count": len(original_coords),
                "simplified_count": len(simplified_coords),
            })

        except Exception as e:
            print(f"  Error: {e}")

    # HTML生成
    html = generate_html(routes_data, mapbox_token)

    output_path = PROJECT_ROOT / "routes_visualization.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n{'='*60}")
    print(f"HTML generated: {output_path}")
    print(f"Open in browser to view the routes.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
