import time
import math
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
NODES_COORDS = {
    'Jakarta_Utara_DC': [-6.1287, 106.8814],
    'Jakarta_Kosambi_DC': [-6.1780, 106.6974],
    'Cirebon_Transit': [-6.7320, 108.5523],
    'Tegal_Transit': [-6.8676, 109.1373],
    'Semarang_DC': [-6.9912, 110.3475],
    'Tuban_Transit': [-6.8976, 112.0649],
    'Surabaya_Osowilangun_DC': [-7.1990, 112.6625],
    'Surabaya_Rungkut_DC': [-7.3312, 112.7588]
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
    """Initialize the Shopee Express logistics network graph"""
    G = nx.Graph()
    
    # Add nodes with coordinates
    for node, coords in NODES_COORDS.items():
        G.add_node(node, pos=coords)
    
    # Add regular arterial routes (non-toll)
    arterial_routes = [
        ('Jakarta_Kosambi_DC', 'Jakarta_Utara_DC', 28, 0, 40),
        ('Jakarta_Utara_DC', 'Cirebon_Transit', 220, 0, 45),
        ('Cirebon_Transit', 'Tegal_Transit', 60, 0, 40),
        ('Tegal_Transit', 'Semarang_DC', 160, 0, 40),
        ('Semarang_DC', 'Tuban_Transit', 210, 0, 45),
        ('Tuban_Transit', 'Surabaya_Osowilangun_DC', 90, 0, 45),
        ('Surabaya_Osowilangun_DC', 'Surabaya_Rungkut_DC', 32, 0, 35),
    ]
    
    for start, end, distance, toll, speed in arterial_routes:
        G.add_edge(start, end, jarak=distance, toll_cost=toll, speed=speed, tipe='arteri')
    
    # Add toll routes (Trans-Java Highway)
    toll_routes = [
        ('Jakarta_Utara_DC', 'Cirebon_Transit', 210, 160000, 80),
        ('Cirebon_Transit', 'Semarang_DC', 230, 180000, 80),
        ('Semarang_DC', 'Surabaya_Osowilangun_DC', 315, 330000, 80),
        ('Semarang_DC', 'Surabaya_Rungkut_DC', 335, 355000, 80),
    ]
    
    for start, end, distance, toll, speed in toll_routes:
        G.add_edge(start, end, jarak=distance, toll_cost=toll, speed=speed, tipe='tol')
    
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

def calculate_route_details(path, departure_time):
    """Calculate detailed metrics for a given route"""
    total_distance = 0
    total_toll = 0
    total_base_time = 0
    multiplier = get_traffic_multiplier(departure_time)
    
    for i in range(len(path) - 1):
        u, v = path[i], path[i+1]
        if G.has_edge(u, v):
            edge_data = G[u][v]
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
# ROUTE CALCULATION FUNCTIONS
# =====================================================================
def calculate_toll_route(origin, destination, departure_time):
    """Calculate route via Trans-Java Toll Highway"""
    if destination == 'Surabaya_Rungkut_DC':
        path = [origin, 'Cirebon_Transit', 'Semarang_DC', 'Surabaya_Rungkut_DC']
    else:
        path = [origin, 'Cirebon_Transit', 'Semarang_DC', 'Surabaya_Osowilangun_DC']
    
    # Add Jakarta_Utara_DC if starting from Kosambi
    if origin == 'Jakarta_Kosambi_DC' and 'Jakarta_Utara_DC' not in path:
        path.insert(1, 'Jakarta_Utara_DC')
    
    return calculate_route_details(path, departure_time)

def calculate_arterial_route(origin, destination, departure_time):
    """Calculate route via Pantura Arterial Road (Non-Toll)"""
    if destination == 'Surabaya_Rungkut_DC':
        path = [origin, 'Cirebon_Transit', 'Tegal_Transit', 'Semarang_DC', 
                'Tuban_Transit', 'Surabaya_Osowilangun_DC', 'Surabaya_Rungkut_DC']
    else:
        path = [origin, 'Cirebon_Transit', 'Tegal_Transit', 'Semarang_DC', 
                'Tuban_Transit', 'Surabaya_Osowilangun_DC']
    
    # Add Jakarta_Utara_DC if starting from Kosambi
    if origin == 'Jakarta_Kosambi_DC' and 'Jakarta_Utara_DC' not in path:
        path.insert(1, 'Jakarta_Utara_DC')
    
    return calculate_route_details(path, departure_time)

def calculate_astar_route(origin, destination, departure_time, optimization):
    """Calculate optimal route using A* algorithm"""
    multiplier = get_traffic_multiplier(departure_time)
    
    if optimization == 'waktu':
        weight_func = lambda u, v, d: (d['jarak'] / d['speed']) * multiplier
        heuristic_func = lambda u, v: (heuristic_haversine_distance(u, v) / MAX_SPEED_GRAPH) * multiplier
    else:
        weight_func = lambda u, v, d: (d['jarak'] * BBM_PER_KM * multiplier) + d['toll_cost']
        heuristic_func = heuristic_cost_estimate
    
    start_time = time.perf_counter()
    path = nx.astar_path(G, source=origin, target=destination, 
                        heuristic=heuristic_func, weight=weight_func)
    computation_time = (time.perf_counter() - start_time) * 1000
    
    result = calculate_route_details(path, departure_time)
    result['waktu_komputasi'] = round(computation_time, 4)
    return result

def calculate_dijkstra_route(origin, destination, departure_time, optimization):
    """Calculate optimal route using Dijkstra algorithm"""
    multiplier = get_traffic_multiplier(departure_time)
    
    if optimization == 'waktu':
        weight_func = lambda u, v, d: (d['jarak'] / d['speed']) * multiplier
    else:
        weight_func = lambda u, v, d: (d['jarak'] * BBM_PER_KM * multiplier) + d['toll_cost']
    
    start_time = time.perf_counter()
    path = nx.dijkstra_path(G, source=origin, target=destination, weight=weight_func)
    computation_time = (time.perf_counter() - start_time) * 1000
    
    result = calculate_route_details(path, departure_time)
    result['waktu_komputasi'] = round(computation_time, 4)
    return result

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
    detail_tol      = calculate_toll_route(asal, tujuan, jam_berangkat)
    detail_arteri   = calculate_arterial_route(asal, tujuan, jam_berangkat)
    detail_astar    = calculate_astar_route(asal, tujuan, jam_berangkat, optimasi)
    detail_dijkstra = calculate_dijkstra_route(asal, tujuan, jam_berangkat, optimasi)

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
        'rekomendasi': rekomendasi
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)