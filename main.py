import streamlit as st
import folium
from streamlit_folium import st_folium
import utils
import time
import math
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
BLOCK_SIZE_KM = 70.0 

PRESET_ZONES = {
    # Europe
    "Paris, France": (48.8566, 2.3522),
    "Lyon, France": (45.7640, 4.8357),
    "Marseille, France": (43.2965, 5.3698),
    "London, UK": (51.5074, -0.1278),
    "Berlin, Germany": (52.5200, 13.4050),
    "Madrid, Spain": (40.4168, -3.7038),
    "Rome, Italy": (41.9028, 12.4964),
    # North America
    "New York, USA": (40.7128, -74.0060),
    "Los Angeles, USA": (34.0522, -118.2437),
    "Chicago, USA": (41.8781, -87.6298),
    "Toronto, Canada": (43.6532, -79.3832),
    # Other
    "Tokyo, Japan": (35.6762, 139.6503),
    "Sydney, Australia": (-33.8688, 151.2093),
    "Dubai, UAE": (25.2048, 55.2708),
}

st.set_page_config(layout="wide", page_title="Google Place Extractor")

# --- SESSION STATE ---
if 'queue' not in st.session_state: st.session_state['queue'] = [] 
if 'processed' not in st.session_state: st.session_state['processed'] = []
if 'results' not in st.session_state: st.session_state['results'] = []
if 'total_calls' not in st.session_state: st.session_state['total_calls'] = 0
if 'sector_counter' not in st.session_state: st.session_state['sector_counter'] = 0

if 'selected_center' not in st.session_state:
    st.session_state['selected_center'] = list(PRESET_ZONES["Paris, France"])
if 'last_zone_selection' not in st.session_state:
    st.session_state['last_zone_selection'] = "Paris, France"

# --- GEOMETRY HELPERS ---
def get_grid_boxes(center_lat, center_lng, n_blocks):
    boxes = []
    d_lat_deg = BLOCK_SIZE_KM / 111.32
    d_lng_deg = BLOCK_SIZE_KM / (111.32 * math.cos(math.radians(center_lat)))
    offset = (n_blocks - 1) / 2.0
    start_lat = center_lat + (offset * d_lat_deg)
    start_lng = center_lng - (offset * d_lng_deg)
    
    for row in range(n_blocks):
        for col in range(n_blocks):
            b_lat = start_lat - (row * d_lat_deg)
            b_lng = start_lng + (col * d_lng_deg)
            half_lat = d_lat_deg / 2
            half_lng = d_lng_deg / 2
            boxes.append((b_lat - half_lat, b_lng - half_lng, b_lat + half_lat, b_lng + half_lng))
    return boxes

def reset_search(n_blocks):
    st.session_state['sector_counter'] = 0
    st.session_state['queue'] = []
    lat, lng = st.session_state['selected_center']
    initial_boxes = get_grid_boxes(lat, lng, n_blocks)
    
    for box in initial_boxes:
        st.session_state['sector_counter'] += 1
        sec_id = f"S-{st.session_state['sector_counter']:06d}"
        st.session_state['queue'].append(box + (sec_id,))
        
    st.session_state['processed'] = []
    st.session_state['results'] = []
    st.session_state['total_calls'] = 0

def get_next_sector_ids(count=4):
    ids = []
    for _ in range(count):
        st.session_state['sector_counter'] += 1
        ids.append(f"S-{st.session_state['sector_counter']:06d}")
    return ids

# --- WORKER FUNCTION ---
def process_single_box_logic(box_data, api_key, keyword, min_radius_limit):
    min_lat, min_lng, max_lat, max_lng, sector_id = box_data
    radius = utils.get_box_radius(min_lat, min_lng, max_lat, max_lng)
    center_lat, center_lng = (min_lat + max_lat) / 2, (min_lng + max_lng) / 2
    
    try:
        places = utils.search_places(api_key, keyword, center_lat, center_lng, radius, max_pages=1)
        count = len(places)
        action = "save"
        if count >= 20 and radius > min_radius_limit: action = "split"
        elif count >= 20 and radius <= min_radius_limit:
            places = utils.search_places(api_key, keyword, center_lat, center_lng, radius, max_pages=3)
            action = "save_dense" 
        return {"status": "ok", "action": action, "places": places, "box_data": box_data, "radius": radius, "count": count}
    except Exception as e: return {"status": "error", "error": str(e), "box_data": box_data}

# --- BATCH MANAGER ---
def run_batch(api_key, keyword, min_radius, max_rps):
    if not st.session_state['queue']: return False
    batch_size = max_rps
    batch_items = [st.session_state['queue'].pop(0) for _ in range(batch_size) if st.session_state['queue']]
    if not batch_items: return False

    results = []
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=batch_size) as executor:
        future_to_box = {executor.submit(process_single_box_logic, item, api_key, keyword, min_radius): item for item in batch_items}
        for future in as_completed(future_to_box): results.append(future.result())
            
    for res in results:
        if res['status'] == 'error':
            st.error(f"Error: {res['error']}")
            continue
        action, box_data, sector_id = res['action'], res['box_data'], res['box_data'][4]
        places, count = res['places'], res['count']
        
        st.session_state['total_calls'] += (1 if action != "save_dense" else 3)
        
        if action == "split":
            min_lat, min_lng, max_lat, max_lng = box_data[:4]
            new_coords = utils.subdivide_box(min_lat, min_lng, max_lat, max_lng)
            new_ids = get_next_sector_ids(4)
            new_boxes = [new_coords[i] + (new_ids[i],) for i in range(4)]
            st.session_state['queue'] = new_boxes + st.session_state['queue']
            st.session_state['processed'].append({'coords': box_data, 'color': '#ff4b4b', 'status': f"Split {sector_id} ({count}+)"})
        else: 
            for p in places: p['source_sector_id'] = sector_id
            st.session_state['results'].extend(places)
            st.session_state['processed'].append({'coords': box_data, 'color': '#0df2c9', 'status': f"Saved {sector_id} ({len(places)})"})

    elapsed = time.time() - start_time
    if elapsed < 1.0: time.sleep(1.0 - elapsed)
    return True

# --- SIDEBAR UI ---
with st.sidebar:
    st.title("⚙️ Paramètres")
    api_key = st.text_input("Clé API Google", type="password", value=utils.load_key())
    keyword = st.text_input("Mot-clé", value="infirmier libéral")
    
    st.divider()
    st.subheader("📍 Zone Géographique")
    
    selected_zone_name = st.selectbox("📍 Preset Location", ["Custom"] + list(PRESET_ZONES.keys()), index=1)
    if selected_zone_name != "Custom" and selected_zone_name != st.session_state['last_zone_selection']:
        st.session_state['selected_center'] = list(PRESET_ZONES[selected_zone_name])
        st.session_state['last_zone_selection'] = selected_zone_name
        st.rerun()

    c1, c2 = st.columns(2)
    with c1: new_lat = st.number_input("Lat", value=st.session_state['selected_center'][0], format="%.4f")
    with c2: new_lng = st.number_input("Lng", value=st.session_state['selected_center'][1], format="%.4f")

    if new_lat != st.session_state['selected_center'][0] or new_lng != st.session_state['selected_center'][1]:
        st.session_state['selected_center'] = [new_lat, new_lng]
        st.session_state['last_zone_selection'] = "Custom"
        st.rerun()
    
    st.divider()
    st.subheader("🚀 Vitesse & Grille")
    min_radius = st.number_input("Rayon Min (m)", value=100)
    limit_rps = st.slider("Requêtes / Seconde", 1, 10, 2)
    grid_n = st.number_input("Taille Grille (N x 70km)", 1, 10, 3)
    
    csv_name = st.text_input("Nom fichier CSV", value="resultats.csv")
    if not csv_name.endswith(".csv"): csv_name += ".csv"
        
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 Réinitialiser"):
            reset_search(grid_n)
            st.rerun()
    with c2:
        if st.button("💾 Sauvegarder"):
             utils.register_full_dataset_to_csv(st.session_state['results'], csv_name)
             st.success(f"Sauvegardé!")

    st.divider()
    st.metric("File d'attente", len(st.session_state['queue']))
    st.metric("Lieux trouvés", len(st.session_state['results']))
    st.metric("Appels API", st.session_state['total_calls'])

# --- MAIN PAGE ---
st.title("🗺️ Scraper")

# --- MODE SÉLECTION DE ZONE (Avant lancement) ---
if not st.session_state['queue'] and not st.session_state['processed']:
    
    # Zone d'information et toggle
    col_info, col_check = st.columns([3, 1])
    col_info.info("📍 Cliquez (Gauche) sur la carte pour déplacer la grille. Cochez la case à droite pour activer.")
    enable_click = col_check.checkbox("🖱️ Activer Déplacement", value=True)
    
    m = folium.Map(location=st.session_state['selected_center'], zoom_start=9)
    
    # Grille de prévisualisation
    preview_boxes = get_grid_boxes(st.session_state['selected_center'][0], st.session_state['selected_center'][1], grid_n)
    
    # Centre (Marker)
    folium.Marker(
        st.session_state['selected_center'], 
        icon=folium.Icon(color="red"), 
        popup="Centre"
    ).add_to(m)
    
    # Dessin des boîtes (CORRECTION ICI : interactive=False)
    for b in preview_boxes:
        folium.Rectangle(
            [[b[0], b[1]], [b[2], b[3]]], 
            color="orange", 
            fill=False, 
            dash_array='5,5',
            interactive=False  # <--- CRUCIAL : Laisse passer le clic à travers le carré
        ).add_to(m)

    output = st_folium(m, width=1200, height=550)
    
    # Gestion du clic
    if enable_click and output['last_clicked']:
        click_lat = output['last_clicked']['lat']
        click_lng = output['last_clicked']['lng']
        
        # On vérifie si le clic est différent (avec une petite marge d'erreur)
        old_lat, old_lng = st.session_state['selected_center']
        if abs(click_lat - old_lat) > 0.0001 or abs(click_lng - old_lng) > 0.0001:
            st.session_state['selected_center'] = [click_lat, click_lng]
            st.session_state['last_zone_selection'] = "Custom"
            st.rerun()

# --- MODE RECHERCHE EN COURS ---
else:
    if st.session_state['queue']:
        focus = st.session_state['queue'][0]
        start_loc = [(focus[0]+focus[2])/2, (focus[1]+focus[3])/2]
    elif st.session_state['processed']:
         last = st.session_state['processed'][-1]['coords']
         start_loc = [(last[0]+last[2])/2, (last[1]+last[3])/2]
    else:
        start_loc = st.session_state['selected_center']

    m = folium.Map(location=start_loc, zoom_start=10)

    # Zones déjà traitées
    for box in st.session_state['processed']:
        folium.Rectangle(
            [[box['coords'][0], box['coords'][1]], [box['coords'][2], box['coords'][3]]],
            color=box['color'], fill=True, fill_opacity=0.1, weight=1
        ).add_to(m)

    # File d'attente
    for i, q_box in enumerate(st.session_state['queue'][:50]):
        color = "blue" if i < limit_rps else "gray" 
        folium.Rectangle(
            [[q_box[0], q_box[1]], [q_box[2], q_box[3]]], 
            color=color, fill=False, weight=1
        ).add_to(m)

    # Résultats
    for p in st.session_state['results']:
        loc = p.get('geometry', {}).get('location')
        if loc: folium.CircleMarker([loc['lat'], loc['lng']], radius=2, color="red", fill=True).add_to(m)

    st_folium(m, width=1200, height=600)

# CONTROLS
st.divider()
c1, c2 = st.columns([1, 4])
is_empty = len(st.session_state['queue']) == 0

with c1:
    if st.button("👟 Pas à Pas (Batch)", disabled=is_empty):
        if api_key:
            run_batch(api_key, keyword, min_radius, limit_rps)
            st.rerun()

with c2:
    run_auto = st.checkbox("▶️ Auto-Run (Turbo)", disabled=is_empty)

if run_auto and not is_empty:
    if api_key:
        run_batch(api_key, keyword, min_radius, limit_rps)
        st.rerun()