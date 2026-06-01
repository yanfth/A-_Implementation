import time
import math
from flask import Flask, render_template, request, jsonify
import networkx as nx
import folium

app = Flask(__name__)

# =====================================================================
# 1. INISIALISASI GRAF JARINGAN LOGISTIK SHOPEE EXPRESS
# =====================================================================
G = nx.Graph()

nodes_coords = {
    'Jakarta_Utara_DC': [-6.1287, 106.8814],
    'Jakarta_Kosambi_DC': [-6.1780, 106.6974],
    'Cirebon_Transit': [-6.7320, 108.5523],
    'Tegal_Transit': [-6.8676, 109.1373],
    'Semarang_DC': [-6.9912, 110.3475],
    'Tuban_Transit': [-6.8976, 112.0649],
    'Surabaya_Osowilangun_DC': [-7.1990, 112.6625],
    'Surabaya_Rungkut_DC': [-7.3312, 112.7588]
}

for node, coords in nodes_coords.items():
    G.add_node(node, pos=coords)

BBM_PER_KM = 5000

# --- JALUR REGULER ARTERI PANTURA (Non-Tol) ---
G.add_edge('Jakarta_Kosambi_DC', 'Jakarta_Utara_DC', jarak=28, toll_cost=0, speed=40, tipe='arteri')
G.add_edge('Jakarta_Utara_DC', 'Cirebon_Transit', jarak=220, toll_cost=0, speed=45, tipe='arteri')
G.add_edge('Cirebon_Transit', 'Tegal_Transit', jarak=60, toll_cost=0, speed=40, tipe='arteri')
G.add_edge('Tegal_Transit', 'Semarang_DC', jarak=160, toll_cost=0, speed=40, tipe='arteri')
G.add_edge('Semarang_DC', 'Tuban_Transit', jarak=210, toll_cost=0, speed=45, tipe='arteri')
G.add_edge('Tuban_Transit', 'Surabaya_Osowilangun_DC', jarak=90, toll_cost=0, speed=45, tipe='arteri')
G.add_edge('Surabaya_Osowilangun_DC', 'Surabaya_Rungkut_DC', jarak=32, toll_cost=0, speed=35, tipe='arteri')

# --- JALUR TOL TRANS-JAWA ---
G.add_edge('Jakarta_Utara_DC', 'Cirebon_Transit', jarak=210, toll_cost=160000, speed=80, tipe='tol')
G.add_edge('Cirebon_Transit', 'Semarang_DC', jarak=230, toll_cost=180000, speed=80, tipe='tol')
G.add_edge('Semarang_DC', 'Surabaya_Osowilangun_DC', jarak=315, toll_cost=330000, speed=80, tipe='tol')
G.add_edge('Semarang_DC', 'Surabaya_Rungkut_DC', jarak=335, toll_cost=355000, speed=80, tipe='tol')

# =====================================================================
# 2. LOGIKA HEURISTIK & MULTIPLIER JAM
# =====================================================================
def heuristic_haversine(u, v):
    pos_u = G.nodes[u]['pos']
    pos_v = G.nodes[v]['pos']
    lat1, lon1 = math.radians(pos_u[0]), math.radians(pos_u[1])
    lat2, lon2 = math.radians(pos_v[0]), math.radians(pos_v[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a_val = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    return 2 * math.asin(math.sqrt(a_val)) * 6371

MAX_SPEED_GRAPH = 80

def heuristic_biaya(u, v):
    return heuristic_haversine(u, v) * BBM_PER_KM

def get_jam_multiplier(jam_pilihan):
    multipliers = {
        '21:00': 1.0,
        '12:00': 1.5,
        '07:00': 1.5,
        '17:00': 2.0
    }
    return multipliers.get(jam_pilihan, 1.0)

def hitung_detail_rute(path, jam_berangkat):
    total_jarak = 0
    total_tol = 0
    total_waktu_dasar = 0
    multiplier = get_jam_multiplier(jam_berangkat)

    for i in range(len(path) - 1):
        # Ambil edge dengan data lengkap (multi-edge handling)
        u, v = path[i], path[i+1]
        if G.has_edge(u, v):
            edge_data = G[u][v]
            total_jarak += edge_data['jarak']
            total_tol += edge_data['toll_cost']
            total_waktu_dasar += edge_data['jarak'] / edge_data['speed']

    total_bbm = total_jarak * BBM_PER_KM
    return {
        'path': " → ".join([n.replace('_', ' ') for n in path]),
        'path_list': path,
        'jarak': round(total_jarak, 1),
        'tol': total_tol,
        'bbm': total_bbm,
        'biaya_total': total_bbm + total_tol,
        'waktu': round(total_waktu_dasar * multiplier, 2)
    }

def hitung_rute_tol(asal, tujuan, jam_berangkat):
    """Rute via Tol Trans-Jawa (lewat Cirebon-Semarang tol)"""
    if tujuan == 'Surabaya_Rungkut_DC':
        path = [asal, 'Cirebon_Transit', 'Semarang_DC', 'Surabaya_Rungkut_DC']
    else:
        path = [asal, 'Cirebon_Transit', 'Semarang_DC', 'Surabaya_Osowilangun_DC']

    if asal == 'Jakarta_Kosambi_DC' and 'Jakarta_Utara_DC' not in path:
        path.insert(1, 'Jakarta_Utara_DC')

    return hitung_detail_rute(path, jam_berangkat)

def hitung_rute_arteri(asal, tujuan, jam_berangkat):
    """Rute via Jalur Arteri Pantura (Non-Tol)"""
    if tujuan == 'Surabaya_Rungkut_DC':
        path = [asal, 'Cirebon_Transit', 'Tegal_Transit', 'Semarang_DC', 'Tuban_Transit', 'Surabaya_Osowilangun_DC', 'Surabaya_Rungkut_DC']
    else:
        path = [asal, 'Cirebon_Transit', 'Tegal_Transit', 'Semarang_DC', 'Tuban_Transit', 'Surabaya_Osowilangun_DC']

    if asal == 'Jakarta_Kosambi_DC' and 'Jakarta_Utara_DC' not in path:
        path.insert(1, 'Jakarta_Utara_DC')

    return hitung_detail_rute(path, jam_berangkat)

def hitung_rute_astar(asal, tujuan, jam_berangkat, optimasi):
    multiplier = get_jam_multiplier(jam_berangkat)
    if optimasi == 'waktu':
        weight_func = lambda u, v, d: (d['jarak'] / d['speed']) * multiplier
        heuristic_func = lambda u, v: (heuristic_haversine(u, v) / MAX_SPEED_GRAPH) * multiplier
    else:
        weight_func = lambda u, v, d: (d['jarak'] * BBM_PER_KM) + d['toll_cost']
        heuristic_func = heuristic_biaya

    start = time.perf_counter()
    path = nx.astar_path(G, source=asal, target=tujuan, heuristic=heuristic_func, weight=weight_func)
    elapsed = (time.perf_counter() - start) * 1000

    detail = hitung_detail_rute(path, jam_berangkat)
    detail['waktu_komputasi'] = round(elapsed, 4)
    return detail

def hitung_rute_dijkstra(asal, tujuan, jam_berangkat, optimasi):
    multiplier = get_jam_multiplier(jam_berangkat)
    if optimasi == 'waktu':
        weight_func = lambda u, v, d: (d['jarak'] / d['speed']) * multiplier
    else:
        weight_func = lambda u, v, d: (d['jarak'] * BBM_PER_KM) + d['toll_cost']

    start = time.perf_counter()
    path = nx.dijkstra_path(G, source=asal, target=tujuan, weight=weight_func)
    elapsed = (time.perf_counter() - start) * 1000

    detail = hitung_detail_rute(path, jam_berangkat)
    detail['waktu_komputasi'] = round(elapsed, 4)
    return detail

# =====================================================================
# 3. ROUTES
# =====================================================================
@app.route('/')
def index():
    asal_options = ['Jakarta_Utara_DC', 'Jakarta_Kosambi_DC']
    tujuan_options = ['Surabaya_Osowilangun_DC', 'Surabaya_Rungkut_DC']
    return render_template('index.html', asal_options=asal_options, tujuan_options=tujuan_options)

@app.route('/hitung', methods=['POST'])
def hitung():
    asal = request.form.get('asal')
    tujuan = request.form.get('tujuan')
    optimasi = request.form.get('optimasi', 'waktu')
    jam_berangkat = request.form.get('jam_berangkat', '21:00')

    # Hitung semua rute
    detail_tol    = hitung_rute_tol(asal, tujuan, jam_berangkat)
    detail_arteri = hitung_rute_arteri(asal, tujuan, jam_berangkat)
    detail_astar  = hitung_rute_astar(asal, tujuan, jam_berangkat, optimasi)
    detail_dijkstra = hitung_rute_dijkstra(asal, tujuan, jam_berangkat, optimasi)

    # Tentukan rekomendasi terbaik berdasarkan optimasi
    if optimasi == 'waktu':
        rekomendasi = 'tol' if detail_tol['waktu'] <= detail_arteri['waktu'] else 'arteri'
    else:
        rekomendasi = 'tol' if detail_tol['biaya_total'] <= detail_arteri['biaya_total'] else 'arteri'

    # --- BUILD FOLIUM MAP ---
    peta = folium.Map(
        location=[-6.9932, 110.4203],
        zoom_start=7,
        tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
        attr='Google Maps'
    )

    # Markers
    for node, coords in nodes_coords.items():
        is_transit = 'Transit' in node
        color = 'green' if node in [asal, tujuan] else 'orange' if not is_transit else 'lightgray'
        icon_name = 'star' if not is_transit else 'circle'
        folium.Marker(
            location=coords,
            popup=node.replace('_', ' '),
            icon=folium.Icon(color=color, icon=icon_name, prefix='fa')
        ).add_to(peta)

    # Jalur Tol (Hijau)
    folium.PolyLine(
        [nodes_coords[n] for n in detail_tol['path_list'] if n in nodes_coords],
        color='#22c55e', weight=6, opacity=0.85, tooltip='Jalur Tol (Hijau)'
    ).add_to(peta)

    # Jalur Arteri (Biru)
    folium.PolyLine(
        [nodes_coords[n] for n in detail_arteri['path_list'] if n in nodes_coords],
        color='#3b82f6', weight=4, opacity=0.85, tooltip='Jalur Arteri / Non-Tol (Biru)'
    ).add_to(peta)

    # A* path (Oranye, tipis di atas)
    folium.PolyLine(
        [nodes_coords[n] for n in detail_astar['path_list'] if n in nodes_coords],
        color='#ff6600', weight=2, opacity=1.0, tooltip='A* Rekomendasi AI'
    ).add_to(peta)

    return jsonify({
        'map_html': peta._repr_html_(),
        'tol': detail_tol,
        'arteri': detail_arteri,
        'astar': detail_astar,
        'dijkstra': detail_dijkstra,
        'rekomendasi': rekomendasi
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)