import time
import math
import heapq
from flask import Flask, render_template, request, jsonify
import networkx as nx
import folium

app = Flask(__name__)

# =====================================================================
# CONSTANTS
# =====================================================================
BBM_PER_KM = 5000
MAX_SPEED_GRAPH = 80

# Node coordinates (lat, lon)
# Catatan: koordinat DC/Hub baru di luar koridor Jakarta-Surabaya adalah titik
# kota/kota besar (bukan alamat gudang persis, karena tidak semua alamat
# gudang SPX dipublikasikan resmi dengan koordinat pasti) -- cukup akurat
# untuk kebutuhan simulasi jaringan & perbandingan algoritma.
NODES_COORDS = {
    # --- Koridor asli: Jakarta - Surabaya (Jawa) ---
    'Jakarta_Utara_DC': [-6.1287, 106.8814],
    'Jakarta_Kosambi_DC': [-6.1780, 106.6974],
    'Cirebon_Transit': [-6.7320, 108.5523],
    'Tegal_Transit': [-6.8676, 109.1373],
    'Semarang_DC': [-6.9912, 110.3475],
    'Tuban_Transit': [-6.8976, 112.0649],
    'Surabaya_Osowilangun_DC': [-7.1990, 112.6625],
    'Surabaya_Rungkut_DC': [-7.3312, 112.7588],

    # --- Tambahan Pulau Jawa ---
    'Bandung_DC': [-6.9175, 107.6191],
    'Yogyakarta_DC': [-7.7956, 110.3695],
    'Malang_DC': [-7.9666, 112.6326],

    # --- Sumatra ---
    'Medan_Hub': [3.5952, 98.6722],
    'Padang_Hub': [-0.9471, 100.4172],
    'Pekanbaru_Hub': [0.5071, 101.4478],
    'Jambi_Hub': [-1.6101, 103.6131],
    'Palembang_DC': [-2.9761, 104.7754],
    'Bengkulu_Hub': [-3.7928, 102.2608],
    'Bandar_Lampung_DC': [-5.4292, 105.2610],
    'Pangkalpinang_Hub': [-2.1316, 106.1169],

    # --- Bali & Nusa Tenggara ---
    'Denpasar_DC': [-8.6705, 115.2126],
    'Kupang_Hub': [-10.1772, 123.6070],

    # --- Kalimantan ---
    'Pontianak_Hub': [-0.0263, 109.3425],
    'Banjarmasin_DC': [-3.3194, 114.5906],
    'Balikpapan_DC': [-1.2379, 116.8529],
    'Tarakan_Hub': [3.3000, 117.6333],

    # --- Sulawesi ---
    'Makassar_DC': [-5.1477, 119.4327],
    'Palu_Hub': [-0.8917, 119.8707],
    'Manado_Hub': [1.4748, 124.8421],

    # --- Maluku & Papua ---
    'Ambon_Hub': [-3.6954, 128.1814],
    'Ternate_Hub': [0.7833, 127.3833],
    'Jayapura_Hub': [-2.5330, 140.7181],
}

JAM_MULTIPLIERS = {
    '21:00': 1.0,   # Malam (lancar)
    '12:00': 1.5,   # Siang (sedang)
    '07:00': 1.5,   # Pagi (sedang)
    '17:00': 2.0    # Sore (macet)
}

# =====================================================================
# NETWORK INITIALIZATION
# =====================================================================
def create_logistics_network():
    """
    Initialize the Shopee Express logistics network graph.

    Menggunakan nx.MultiGraph (bukan nx.Graph biasa) karena banyak pasang
    kota di jaringan ini punya DUA jalur paralel (tol & arteri) sekaligus,
    misalnya Jakarta<->Bandung. Kalau pakai nx.Graph biasa, edge kedua yang
    ditambahkan akan MENIMPA data edge pertama (nx.Graph cuma mengizinkan
    1 edge per pasang node) -- sehingga salah satu jalur (mis. arterinya)
    akan hilang diam-diam. MultiGraph mengizinkan beberapa edge berbeda
    (dibedakan lewat 'key') antara dua node yang sama.
    """
    G = nx.MultiGraph()

    # Add nodes with coordinates
    for node, coords in NODES_COORDS.items():
        G.add_node(node, pos=coords)

    # Add regular arterial routes (non-toll)
    arterial_routes = [
        # --- Koridor asli Jawa ---
        ('Jakarta_Kosambi_DC', 'Jakarta_Utara_DC', 28, 0, 40),
        ('Jakarta_Utara_DC', 'Cirebon_Transit', 220, 0, 45),
        ('Cirebon_Transit', 'Tegal_Transit', 60, 0, 40),
        ('Tegal_Transit', 'Semarang_DC', 160, 0, 40),
        ('Semarang_DC', 'Tuban_Transit', 210, 0, 45),
        ('Tuban_Transit', 'Surabaya_Osowilangun_DC', 90, 0, 45),
        ('Surabaya_Osowilangun_DC', 'Surabaya_Rungkut_DC', 32, 0, 35),

        # --- Perluasan Pulau Jawa (jalur arteri, non-tol) ---
        ('Jakarta_Utara_DC', 'Bandung_DC', 180, 0, 45),
        ('Bandung_DC', 'Semarang_DC', 390, 0, 40),
        ('Semarang_DC', 'Yogyakarta_DC', 130, 0, 40),
        ('Yogyakarta_DC', 'Malang_DC', 320, 0, 40),
        ('Malang_DC', 'Surabaya_Osowilangun_DC', 95, 0, 40),

        # --- Sumatra (Jalan Lintas Sumatra, belum ada tol menyeluruh) ---
        ('Medan_Hub', 'Pekanbaru_Hub', 620, 0, 40),
        ('Pekanbaru_Hub', 'Padang_Hub', 240, 0, 40),
        ('Pekanbaru_Hub', 'Jambi_Hub', 430, 0, 40),
        ('Jambi_Hub', 'Palembang_DC', 260, 0, 40),
        ('Palembang_DC', 'Bengkulu_Hub', 350, 0, 35),
        ('Palembang_DC', 'Bandar_Lampung_DC', 360, 0, 45),

        # --- Kalimantan (Jalan Trans-Kalimantan, medan berat -> kecepatan lebih rendah) ---
        ('Pontianak_Hub', 'Banjarmasin_DC', 850, 0, 35),
        ('Banjarmasin_DC', 'Balikpapan_DC', 420, 0, 40),

        # --- Sulawesi (Jalan Trans-Sulawesi, pegunungan) ---
        ('Makassar_DC', 'Palu_Hub', 600, 0, 35),
        ('Palu_Hub', 'Manado_Hub', 750, 0, 35),
    ]

    for start, end, distance, toll, speed in arterial_routes:
        G.add_edge(start, end, key='arteri', jarak=distance, toll_cost=toll, speed=speed, tipe='arteri')

    # Add toll routes (Trans-Java Highway -- saat ini tol baru ada di Jawa)
    toll_routes = [
        ('Jakarta_Utara_DC', 'Cirebon_Transit', 210, 160000, 80),
        ('Cirebon_Transit', 'Semarang_DC', 230, 180000, 80),
        ('Semarang_DC', 'Surabaya_Osowilangun_DC', 315, 330000, 80),
        ('Semarang_DC', 'Surabaya_Rungkut_DC', 335, 355000, 80),

        # --- Perluasan tol Jawa ---
        ('Jakarta_Utara_DC', 'Bandung_DC', 150, 116000, 80),
        ('Bandung_DC', 'Semarang_DC', 370, 300000, 80),
        ('Semarang_DC', 'Yogyakarta_DC', 115, 95000, 80),
        ('Malang_DC', 'Surabaya_Osowilangun_DC', 95, 78000, 80),
    ]

    for start, end, distance, toll, speed in toll_routes:
        G.add_edge(start, end, key='tol', jarak=distance, toll_cost=toll, speed=speed, tipe='tol')

    # Add sea/ferry crossings (penyeberangan laut antar-pulau) -- satu-satunya
    # cara menyambungkan pulau yang tidak terhubung jalan darat. Kecepatan
    # efektif dibuat rendah (25-30 km/jam) karena mencakup waktu bongkar-muat
    # dan pelayaran, bukan cuma waktu jalan murni.
    laut_routes = [
        ('Palembang_DC', 'Pangkalpinang_Hub', 195, 150000, 25),
        ('Bandar_Lampung_DC', 'Jakarta_Utara_DC', 220, 200000, 30),
        ('Surabaya_Rungkut_DC', 'Denpasar_DC', 350, 250000, 30),
        ('Denpasar_DC', 'Kupang_Hub', 1050, 600000, 30),
        ('Jakarta_Utara_DC', 'Pontianak_Hub', 820, 450000, 28),
        ('Surabaya_Osowilangun_DC', 'Banjarmasin_DC', 540, 350000, 30),
        ('Balikpapan_DC', 'Tarakan_Hub', 580, 300000, 28),
        ('Balikpapan_DC', 'Makassar_DC', 590, 350000, 30),
        ('Makassar_DC', 'Ambon_Hub', 1100, 550000, 30),
        ('Ambon_Hub', 'Ternate_Hub', 570, 300000, 28),
        ('Ambon_Hub', 'Jayapura_Hub', 1550, 750000, 30),
    ]

    for start, end, distance, toll, speed in laut_routes:
        G.add_edge(start, end, key='laut', jarak=distance, toll_cost=toll, speed=speed, tipe='laut')

    return G

G = create_logistics_network()

# =====================================================================
# UTILITY FUNCTIONS
# =====================================================================
def heuristic_haversine_distance(u, v):
    """Calculate Haversine distance between two nodes"""
    pos_u = G.nodes[u]['pos']
    pos_v = G.nodes[v]['pos']
    lat1, lon1 = math.radians(pos_u[0]), math.radians(pos_u[1])
    lat2, lon2 = math.radians(pos_v[0]), math.radians(pos_v[1])

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a_val = (math.sin(dlat / 2)**2 +
             math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2)

    return 2 * math.asin(math.sqrt(a_val)) * 6371  # Earth radius in km

def heuristic_cost_estimate(u, v):
    """Calculate cost heuristic between two nodes"""
    return heuristic_haversine_distance(u, v) * BBM_PER_KM

def get_traffic_multiplier(departure_time):
    """Get traffic multiplier based on departure time"""
    return JAM_MULTIPLIERS.get(departure_time, 1.0)

def calculate_route_details(path, departure_time, edge_keys=None, allowed_types=None):
    """
    Calculate detailed metrics for a given route.

    edge_keys: list opsional berisi key edge ('arteri'/'tol'/'laut') yang
    dipakai di tiap hop path -- dipakai supaya angka jarak/biaya/waktu yang
    ditampilkan PERSIS mengikuti edge yang benar-benar dipilih algoritma A*/
    Dijkstra (penting sejak graf jadi MultiGraph, karena satu pasang node
    bisa punya lebih dari satu edge paralel).

    allowed_types: set opsional, mis. {'tol','laut'} -- dipakai oleh
    calculate_toll_route/calculate_arterial_route supaya di antara edge
    paralel yang tersedia, yang dipilih adalah yang tipenya sesuai (BUKAN
    sekadar yang jaraknya terpendek -- sempat jadi bug: rute "arteri" bisa
    salah pilih edge 'tol' kalau kebetulan jaraknya lebih pendek).
    """
    total_distance = 0
    total_toll = 0
    total_base_time = 0
    multiplier = get_traffic_multiplier(departure_time)

    for i in range(len(path) - 1):
        u, v = path[i], path[i+1]
        if G.has_edge(u, v):
            parallel_edges = G[u][v]  # dict {key: data} pada MultiGraph
            if edge_keys is not None and edge_keys[i] in parallel_edges:
                edge_data = parallel_edges[edge_keys[i]]
            elif allowed_types is not None:
                candidates = [d for d in parallel_edges.values() if d['tipe'] in allowed_types]
                edge_data = min(candidates or parallel_edges.values(), key=lambda d: d['jarak'])
            else:
                edge_data = min(parallel_edges.values(), key=lambda d: d['jarak'])
            total_distance += edge_data['jarak']
            total_toll += edge_data['toll_cost']
            total_base_time += edge_data['jarak'] / edge_data['speed']

    # Calculate fuel cost with traffic multiplier (traffic affects fuel consumption)
    base_fuel_cost = total_distance * BBM_PER_KM
    total_fuel_cost = round(base_fuel_cost * multiplier)

    return {
        'path': " → ".join([n.replace('_', ' ') for n in path]),
        'path_list': path,
        'jarak': round(total_distance, 1),
        'tol': total_toll,  # Toll cost remains constant
        'bbm': total_fuel_cost,  # Fuel cost affected by traffic
        'biaya_total': total_fuel_cost + total_toll,
        'waktu': round(total_base_time * multiplier, 2)
    }

# =====================================================================
# CUSTOM SEARCH ALGORITHMS (dengan tracking node yang dieksplorasi)
# =====================================================================
def astar_with_tracking(G, source, target, heuristic, weight):
    """
    Implementasi A* manual menggunakan heapq, agar kita bisa menghitung
    dengan pasti berapa banyak node yang benar-benar di-'pop' (dieksplorasi)
    dari priority queue -- ini yang jadi bukti konkret efisiensi A*
    dibanding Dijkstra, bukan cuma selisih waktu komputasi dalam ms.
    """
    counter = 0  # tie-breaker biar heapq tidak membandingkan node secara langsung
    frontier = [(heuristic(source, target), counter, source)]
    came_from = {}
    cost_so_far = {source: 0}
    visited = set()
    expanded_nodes = 0

    while frontier:
        _, _, current = heapq.heappop(frontier)

        if current in visited:
            continue
        visited.add(current)
        expanded_nodes += 1

        if current == target:
            break

        for neighbor in G.neighbors(current):
            if neighbor in visited:
                continue
            # MultiGraph: bisa ada beberapa edge paralel (arteri/tol/laut)
            # ke tetangga yang sama -- pilih yang memberi cost terendah
            parallel_edges = G[current][neighbor]
            best_key, best_cost = None, None
            for edge_key, edge_data in parallel_edges.items():
                candidate_cost = cost_so_far[current] + weight(current, neighbor, edge_data)
                if best_cost is None or candidate_cost < best_cost:
                    best_cost, best_key = candidate_cost, edge_key
            new_cost = best_cost

            if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                cost_so_far[neighbor] = new_cost
                priority = new_cost + heuristic(neighbor, target)
                counter += 1
                heapq.heappush(frontier, (priority, counter, neighbor))
                came_from[neighbor] = (current, best_key)

    if target != source and target not in came_from:
        raise nx.NetworkXNoPath(f"Tidak ada jalur antara {source} dan {target}")

    path = [target]
    edge_keys = []
    while path[-1] != source:
        parent, key_used = came_from[path[-1]]
        edge_keys.append(key_used)
        path.append(parent)
    path.reverse()
    edge_keys.reverse()

    return path, edge_keys, expanded_nodes


def dijkstra_with_tracking(G, source, target, weight):
    """
    Implementasi Dijkstra manual dengan struktur yang sama persis dengan
    astar_with_tracking di atas (hanya tanpa heuristic), supaya perbandingan
    jumlah node yang dieksplorasi adil (apple-to-apple).
    """
    counter = 0
    frontier = [(0, counter, source)]
    came_from = {}
    cost_so_far = {source: 0}
    visited = set()
    expanded_nodes = 0

    while frontier:
        current_cost, _, current = heapq.heappop(frontier)

        if current in visited:
            continue
        visited.add(current)
        expanded_nodes += 1

        if current == target:
            break

        for neighbor in G.neighbors(current):
            if neighbor in visited:
                continue
            parallel_edges = G[current][neighbor]
            best_key, best_cost = None, None
            for edge_key, edge_data in parallel_edges.items():
                candidate_cost = cost_so_far[current] + weight(current, neighbor, edge_data)
                if best_cost is None or candidate_cost < best_cost:
                    best_cost, best_key = candidate_cost, edge_key
            new_cost = best_cost

            if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                cost_so_far[neighbor] = new_cost
                counter += 1
                heapq.heappush(frontier, (new_cost, counter, neighbor))
                came_from[neighbor] = (current, best_key)

    if target != source and target not in came_from:
        raise nx.NetworkXNoPath(f"Tidak ada jalur antara {source} dan {target}")

    path = [target]
    edge_keys = []
    while path[-1] != source:
        parent, key_used = came_from[path[-1]]
        edge_keys.append(key_used)
        path.append(parent)
    path.reverse()
    edge_keys.reverse()

    return path, edge_keys, expanded_nodes

# =====================================================================
# ROUTE CALCULATION FUNCTIONS
# =====================================================================
def _shortest_path_by_edge_types(origin, destination, allowed_types):
    """
    Cari jalur terpendek (berdasarkan jarak km) yang hanya melewati edge
    dengan 'tipe' termasuk dalam allowed_types. Ini murni pencarian shortest
    path biasa (nx.dijkstra_path) untuk keperluan kartu perbandingan "Jalur
    Tol" vs "Jalur Arteri" -- BUKAN bagian dari algoritma A*/Dijkstra utama
    yang dibandingkan di tabel evaluasi (itu tetap pakai astar_with_tracking
    dan dijkstra_with_tracking, tidak diubah sama sekali).

    Perlu digeneralisasi (sebelumnya hardcoded path Jakarta->Surabaya) karena
    dengan puluhan node baru se-Indonesia, path tetap tidak mungkin lagi
    ditulis manual satu per satu.
    """
    subgraph_edges = [
        (u, v, k) for u, v, k, d in G.edges(keys=True, data=True) if d['tipe'] in allowed_types
    ]
    subgraph = G.edge_subgraph(subgraph_edges)

    if origin not in subgraph or destination not in subgraph or \
       not nx.has_path(subgraph, origin, destination):
        # Fallback: kalau tidak ada jalur dengan tipe yang diminta (mis. tol
        # belum ada di luar Jawa), pakai seluruh graf supaya tetap ada hasil
        subgraph = G

    return nx.dijkstra_path(subgraph, source=origin, target=destination, weight='jarak')

def calculate_toll_route(origin, destination, departure_time):
    """Calculate route via toll roads (Jawa) + penyeberangan laut antar-pulau"""
    allowed = {'tol', 'laut'}
    path = _shortest_path_by_edge_types(origin, destination, allowed_types=allowed)
    return calculate_route_details(path, departure_time, allowed_types=allowed)

def calculate_arterial_route(origin, destination, departure_time):
    """Calculate route via arterial/non-toll roads + penyeberangan laut antar-pulau"""
    allowed = {'arteri', 'laut'}
    path = _shortest_path_by_edge_types(origin, destination, allowed_types=allowed)
    return calculate_route_details(path, departure_time, allowed_types=allowed)

def calculate_astar_route(origin, destination, departure_time, optimization):
    """Calculate optimal route using A* algorithm (dengan tracking node dieksplorasi)"""
    multiplier = get_traffic_multiplier(departure_time)

    if optimization == 'waktu':
        weight_func = lambda u, v, d: (d['jarak'] / d['speed']) * multiplier
        heuristic_func = lambda u, v: (heuristic_haversine_distance(u, v) / MAX_SPEED_GRAPH) * multiplier
    else:
        weight_func = lambda u, v, d: (d['jarak'] * BBM_PER_KM * multiplier) + d['toll_cost']
        heuristic_func = heuristic_cost_estimate

    start_time = time.perf_counter()
    path, edge_keys, expanded_nodes = astar_with_tracking(
        G, source=origin, target=destination,
        heuristic=heuristic_func, weight=weight_func
    )
    computation_time = (time.perf_counter() - start_time) * 1000

    result = calculate_route_details(path, departure_time, edge_keys=edge_keys)
    result['waktu_komputasi'] = round(computation_time, 4)
    result['node_dieksplorasi'] = expanded_nodes
    result['total_node_graf'] = G.number_of_nodes()
    return result

def calculate_dijkstra_route(origin, destination, departure_time, optimization):
    """Calculate optimal route using Dijkstra algorithm (dengan tracking node dieksplorasi)"""
    multiplier = get_traffic_multiplier(departure_time)

    if optimization == 'waktu':
        weight_func = lambda u, v, d: (d['jarak'] / d['speed']) * multiplier
    else:
        weight_func = lambda u, v, d: (d['jarak'] * BBM_PER_KM * multiplier) + d['toll_cost']

    start_time = time.perf_counter()
    path, edge_keys, expanded_nodes = dijkstra_with_tracking(
        G, source=origin, target=destination, weight=weight_func
    )
    computation_time = (time.perf_counter() - start_time) * 1000

    result = calculate_route_details(path, departure_time, edge_keys=edge_keys)
    result['waktu_komputasi'] = round(computation_time, 4)
    result['node_dieksplorasi'] = expanded_nodes
    result['total_node_graf'] = G.number_of_nodes()
    return result

# =====================================================================
# 3. ROUTES
# =====================================================================
@app.route('/')
def index():
    # Semua node (DC/Hub) di seluruh Indonesia kini tersedia di kedua dropdown
    semua_node = sorted(NODES_COORDS.keys())
    asal_options = semua_node
    tujuan_options = semua_node
    return render_template('index.html', asal_options=asal_options, tujuan_options=tujuan_options)

@app.route('/hitung', methods=['POST'])
def hitung():
    asal = request.form.get('asal')
    tujuan = request.form.get('tujuan')
    optimasi = request.form.get('optimasi', 'waktu')
    jam_berangkat = request.form.get('jam_berangkat', '21:00')

    # Hitung semua rute
    detail_tol      = calculate_toll_route(asal, tujuan, jam_berangkat)
    detail_arteri   = calculate_arterial_route(asal, tujuan, jam_berangkat)
    detail_astar    = calculate_astar_route(asal, tujuan, jam_berangkat, optimasi)
    detail_dijkstra = calculate_dijkstra_route(asal, tujuan, jam_berangkat, optimasi)

    # Tentukan rekomendasi terbaik berdasarkan optimasi
    if optimasi == 'waktu':
        rekomendasi = 'tol' if detail_tol['waktu'] <= detail_arteri['waktu'] else 'arteri'
    else:
        rekomendasi = 'tol' if detail_tol['biaya_total'] <= detail_arteri['biaya_total'] else 'arteri'

    # Efisiensi eksplorasi A* dibanding Dijkstra (dalam persen)
    if detail_dijkstra['node_dieksplorasi'] > 0:
        efisiensi_eksplorasi = round(
            (1 - detail_astar['node_dieksplorasi'] / detail_dijkstra['node_dieksplorasi']) * 100, 1
        )
    else:
        efisiensi_eksplorasi = 0

    # --- BUILD FOLIUM MAP ---
    peta = folium.Map(
        location=[-6.9932, 110.4203],
        zoom_start=7,
        tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
        attr='Google Maps'
    )

    # Markers
    for node, coords in NODES_COORDS.items():
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
        [NODES_COORDS[n] for n in detail_tol['path_list'] if n in NODES_COORDS],
        color='#22c55e', weight=6, opacity=0.85, tooltip='Jalur Tol (Hijau)'
    ).add_to(peta)

    # Jalur Arteri (Biru)
    folium.PolyLine(
        [NODES_COORDS[n] for n in detail_arteri['path_list'] if n in NODES_COORDS],
        color='#3b82f6', weight=4, opacity=0.85, tooltip='Jalur Arteri / Non-Tol (Biru)'
    ).add_to(peta)

    # A* path (Oranye, tipis di atas)
    folium.PolyLine(
        [NODES_COORDS[n] for n in detail_astar['path_list'] if n in NODES_COORDS],
        color='#ff6600', weight=2, opacity=1.0, tooltip='A* Rekomendasi AI'
    ).add_to(peta)

    return jsonify({
        'map_html': peta._repr_html_(),
        'tol': detail_tol,
        'arteri': detail_arteri,
        'astar': detail_astar,
        'dijkstra': detail_dijkstra,
        'rekomendasi': rekomendasi,
        'efisiensi_eksplorasi': efisiensi_eksplorasi
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)