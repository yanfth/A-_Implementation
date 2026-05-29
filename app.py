import time
import math
from flask import Flask, render_template, request, jsonify
import networkx as nx
import folium

app = Flask(__name__)

# ==========================================
# 1. INSIALISASI GRAF JARINGAN SHOPEE EXPRESS DC
# ==========================================
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

# Jalur Reguler Pantura (Non-Tol)
G.add_edge('Jakarta_Utara_DC', 'Cirebon_Transit', jarak=220, toll_cost=0, speed=45)
G.add_edge('Jakarta_Kosambi_DC', 'Cirebon_Transit', jarak=245, toll_cost=0, speed=45)
G.add_edge('Cirebon_Transit', 'Tegal_Transit', jarak=60, toll_cost=0, speed=40)
G.add_edge('Tegal_Transit', 'Semarang_DC', jarak=160, toll_cost=0, speed=40)
G.add_edge('Semarang_DC', 'Tuban_Transit', jarak=210, toll_cost=0, speed=45)
G.add_edge('Tuban_Transit', 'Surabaya_Osowilangun_DC', jarak=90, toll_cost=0, speed=45)
G.add_edge('Surabaya_Osowilangun_DC', 'Surabaya_Rungkut_DC', jarak=32, toll_cost=0, speed=35)

# Jalur Tol Trans-Jawa Darat
G.add_edge('Jakarta_Utara_DC', 'Cirebon_Transit', jarak=210, toll_cost=160000, speed=80) 
G.add_edge('Cirebon_Transit', 'Semarang_DC', jarak=230, toll_cost=180000, speed=80)
G.add_edge('Semarang_DC', 'Surabaya_Osowilangun_DC', jarak=315, toll_cost=330000, speed=80)
G.add_edge('Semarang_DC', 'Surabaya_Rungkut_DC', jarak=335, toll_cost=355000, speed=80)

# ==========================================
# 2. LOGIKA HEURISTIK & MULTIPLIER KONDISI
# ==========================================
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

def heuristic_waktu(u, v):
    return heuristic_haversine(u, v) / MAX_SPEED_GRAPH

def heuristic_biaya(u, v):
    return heuristic_haversine(u, v) * BBM_PER_KM

# Fungsi menghitung detail hasil akhir dengan penambahan kondisi Traffic & Overload
def hitung_detail_rute(path, status_lalin, status_gudang):
    total_jarak = 0
    total_tol = 0
    total_waktu = 0
    total_delay_gudang = 0
    total_biaya_overload = 0
    
    # Menghitung jumlah node transit di tengah perjalanan (bukan asal/tujuan)
    jumlah_node_transit = max(0, len(path) - 2)
    
    if status_gudang == 'padat':
        total_delay_gudang = jumlah_node_transit * 2        # Tambah 2 jam per node transit
        total_biaya_overload = jumlah_node_transit * 500000  # Tambah Rp 500.000 per node transit

    for i in range(len(path) - 1):
        edge_data = G[path[i]][path[i+1]]
        total_jarak += edge_data['jarak']
        total_tol += edge_data['toll_cost']
        
        # Pengaruh Traffic pada Kecepatan
        kecepatan_efektif = edge_data['speed'] * 0.5 if status_lalin == 'macet' else edge_data['speed']
        total_waktu += edge_data['jarak'] / kecepatan_efektif
        
    total_bbm = total_jarak * BBM_PER_KM
    total_biaya = total_bbm + total_tol + total_biaya_overload
    total_waktu_akhir = total_waktu + total_delay_gudang
    
    return {
        'path': path,
        'jarak': round(total_jarak, 1),
        'tol': total_tol,
        'bbm': total_bbm,
        'biaya_overload': total_biaya_overload,
        'biaya_total': total_biaya,
        'waktu': round(total_waktu_akhir, 2),
        'delay_gudang': total_delay_gudang
    }

def hitung_rute_asli_shopee(asal, tujuan, status_lalin, status_gudang):
    if asal in ['Jakarta_Utara_DC', 'Jakarta_Kosambi_DC'] and tujuan == 'Surabaya_Osowilangun_DC':
        path = [asal, 'Cirebon_Transit', 'Tegal_Transit', 'Semarang_DC', 'Tuban_Transit', 'Surabaya_Osowilangun_DC']
    else:
        path = [asal, 'Cirebon_Transit', 'Tegal_Transit', 'Semarang_DC', 'Tuban_Transit', 'Surabaya_Osowilangun_DC', 'Surabaya_Rungkut_DC']
    return hitung_detail_rute(path, status_lalin, status_gudang)

@app.route('/')
def index():
    asal_options = ['Jakarta_Utara_DC', 'Jakarta_Kosambi_DC']
    tujuan_options = ['Surabaya_Osowilangun_DC', 'Surabaya_Rungkut_DC']
    return render_template('index.html', asal_options=asal_options, tujuan_options=tujuan_options)

@app.route('/hitung', methods=['POST'])
def hitung():
    asal = request.form.get('asal', 'Jakarta_Utara_DC')
    tujuan = request.form.get('tujuan', 'Surabaya_Osowilangun_DC')
    optimasi = request.form.get('optimasi', 'waktu')
    
    # Menangkap Parameter Simulasi Baru dari Form Parameter
    status_lalin = request.form.get('lalin', 'lancar')      # lancar / macet
    status_gudang = request.form.get('gudang', 'normal')    # normal / padat
    
    # Fungsi pembobotan dinamis NetworkX berdasarkan pilihan user
    if optimasi == 'waktu':
        if status_lalin == 'macet':
            weight_func = lambda u, v, d: d['jarak'] / (d['speed'] * 0.5)
        else:
            weight_func = lambda u, v, d: d['jarak'] / d['speed']
    else:
        weight_func = lambda u, v, d: (d['jarak'] * BBM_PER_KM) + d['toll_cost']
        
    # Eksekusi Algoritma
    start_dijkstra = time.perf_counter()
    path_dijkstra = nx.dijkstra_path(G, source=asal, target=tujuan, weight=weight_func)
    end_dijkstra = time.perf_counter()
    waktu_komputasi_dijkstra = (end_dijkstra - start_dijkstra) * 1000
    
    heuristic_func = heuristic_waktu if optimasi == 'waktu' else heuristic_biaya
    start_astar = time.perf_counter()
    path_astar = nx.astar_path(G, source=asal, target=tujuan, heuristic=heuristic_func, weight=weight_func)
    end_astar = time.perf_counter()
    waktu_komputasi_astar = (end_astar - start_astar) * 1000
    
    # Proses Kalkulasi Detail Output
    detail_astar = hitung_detail_rute(path_astar, status_lalin, status_gudang)
    detail_dijkstra = hitung_detail_rute(path_dijkstra, status_lalin, status_gudang)
    detail_shopee = hitung_rute_asli_shopee(asal, tujuan, status_lalin, status_gudang)
    
    return render_template('rute.html', 
                           optimasi=optimasi, status_lalin=status_lalin, status_gudang=status_gudang,
                           astar=detail_astar, dijkstra=detail_dijkstra, shopee=detail_shopee,
                           waktu_astar=round(waktu_komputasi_astar, 4),
                           waktu_dijkstra=round(waktu_komputasi_dijkstra, 4),
                           asal=asal, tujuan=tujuan)

@app.route('/peta_render')
def peta_render():
    asal = request.args.get('asal', 'Jakarta_Utara_DC')
    tujuan = request.args.get('tujuan', 'Surabaya_Osowilangun_DC')
    path_astar = request.args.get('path_astar', '').split(',') if request.args.get('path_astar', '') else []
    path_dijkstra = request.args.get('path_dijkstra', '').split(',') if request.args.get('path_dijkstra', '') else []
    path_shopee = request.args.get('path_shopee', '').split(',') if request.args.get('path_shopee', '') else []
    
    google_maps_tiles = 'https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}'
    peta = folium.Map(location=[-6.9932, 110.4203], zoom_start=7, tiles=google_maps_tiles, attr='Google Maps')
    
    for node, coords in nodes_coords.items():
        is_transit = 'Transit' in node
        color = 'green' if node in [asal, tujuan] else 'orange' if not is_transit else 'lightgray'
        folium.Marker(location=coords, popup=node.replace('_', ' '), icon=folium.Icon(color=color, icon='star' if not is_transit else 'circle', prefix='fa')).add_to(peta)
    
    if path_dijkstra:
        folium.PolyLine([nodes_coords[n] for n in path_dijkstra if n in nodes_coords], color='#64748b', weight=7, opacity=0.5).add_to(peta)
    if path_shopee:
        folium.PolyLine([nodes_coords[n] for n in path_shopee if n in nodes_coords], color='#dc2626', weight=4, opacity=0.8).add_to(peta)
    if path_astar:
        folium.PolyLine([nodes_coords[n] for n in path_astar if n in nodes_coords], color='#ff6600', weight=3, opacity=1.0).add_to(peta)
        
    return peta._repr_html_()

if __name__ == '__main__':
    app.run(debug=True, port=5000)