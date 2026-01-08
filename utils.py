import unittest
import dotenv
import os
from loguru import logger
from datetime import datetime
import json
import csv
import requests
import time
import math
import pandas as pd

import numpy as np
# Load the API key from the .env file
def load_key() -> str:
    dotenv.load_dotenv()
    key = os.getenv("GOOGLE_KEY")
    return key

def log_api_call(keyword: str, lat: float, lng: float, radius: float, filepath: str = "api_logs.csv", response: dict = None):
    """
    Logs the API call and the response to the standard logger and to a CSV file.
    """
    # 1. Existing Logger
    logger.info(f"API Call: {keyword} - {lat}, {lng} - {radius}")

    # 2. CSV Handling
    file_exists = os.path.isfile(filepath)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Serialize the response dict to a JSON string
    response_str = json.dumps(response) if response else ""

    try:
        with open(filepath, mode='a', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['timestamp', 'keyword', 'latitude', 'longitude', 'radius', 'response']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()

            writer.writerow({
                'timestamp': current_time,
                'keyword': keyword,
                'latitude': lat,
                'longitude': lng,
                'radius': radius,
                'response': response_str
            })
    except IOError as e:
        logger.error(f"Error writing to CSV: {e}")

def search_places(api_key: str, keyword: str, lat: float, lng: float, radius: float, max_pages: int = 1) -> list:
    """
    Searches for places and handles pagination to fetch up to 60 results.
    """
    base_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    
    all_places = [] 
    next_page_token = None

    for page_num in range(max_pages):
        params = {
            'key': api_key,
            'location': f"{lat},{lng}",
            'radius': radius,
            'keyword': keyword
        }

        if next_page_token:
            params['pagetoken'] = next_page_token
            # CRITICAL: Google needs a moment to generate the next page.
            time.sleep(2) 

        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            log_api_call(keyword, lat, lng, radius, response=data)

            current_results = data.get('results', [])
            all_places.extend(current_results)
            
            next_page_token = data.get('next_page_token')

            if not next_page_token:
                break
                
        except requests.exceptions.RequestException as e:
            print(f"Error on page {page_num + 1}: {e}")
            break

    return all_places

# --- VERSION 2 : Classe Optimisée (Pour traiter toute la France) ---
class PopulationAnalyzer:
    def __init__(self, csv_path="france_population.csv"):
        """
        Charge un fichier CSV (X, Y, Z) en mémoire RAM sous forme de matrices NumPy.
        Beaucoup plus simple et fiable que le TIFF.
        """
        print(f"⏳ Chargement du CSV population : {csv_path}...")
        
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"❌ Fichier introuvable : {csv_path}")

        # 1. Lecture rapide avec Pandas
        # On s'attend à : X (Lon), Y (Lat), Z (Pop)
        try:
            df = pd.read_csv(csv_path)
            
            # Nettoyage des noms de colonnes (au cas où il y a des espaces)
            df.columns = df.columns.str.strip().str.upper()
            
            # Vérification des colonnes
            required = {'X', 'Y', 'Z'}
            if not required.issubset(df.columns):
                 raise ValueError(f"Le CSV doit contenir les colonnes X, Y, Z. Trouvé : {df.columns}")

            # 2. Conversion en tableaux NumPy (Pour la vitesse extrême)
            # On stocke Lat, Lon et Pop dans des vecteurs séparés
            self.lons = df['X'].to_numpy(dtype=np.float32)
            self.lats = df['Y'].to_numpy(dtype=np.float32)
            self.pops = df['Z'].to_numpy(dtype=np.float32)
            
            self.count = len(self.lons)
            print(f"✅ {self.count:,} points de données chargés en mémoire !")
            
        except Exception as e:
            print(f"❌ Erreur lors de la lecture du CSV : {e}")
            raise

    def get_population(self, lat: float, lon: float, size_km: float) -> int:
        """
        Trouve tous les points dans le carré et fait la somme.
        Utilise des filtres NumPy (très rapide).
        """
        # 1. Convertir la taille (km) en degrés (approximatif mais suffisant)
        # 1 degré Latitude ~= 111.32 km
        # 1 degré Longitude ~= 111.32 * cos(lat)
        
        radius_km = size_km / 2.0
        
        delta_lat = radius_km / 111.32
        delta_lon = radius_km / (111.32 * math.cos(math.radians(lat)))
        
        min_lat = lat - delta_lat
        max_lat = lat + delta_lat
        min_lon = lon - delta_lon
        max_lon = lon + delta_lon
        
        # 2. Filtrage vectoriel (C'est ici que la magie opère)
        # On crée un masque : "Garde les points qui sont entre min et max"
        # C'est instantané grâce à NumPy
        mask = (
            (self.lats >= min_lat) & (self.lats <= max_lat) & 
            (self.lons >= min_lon) & (self.lons <= max_lon)
        )
        
        # 3. Somme des populations qui correspondent au masque
        total_pop = np.sum(self.pops[mask])
        
        return int(total_pop)

def register_full_dataset_to_csv(new_places_list: list, filename: str = "full_places_dataset.csv"):
    """
    Saves the raw Google Places data to a CSV file.
    
    - Keeps ALL columns (geometry, photos, opening_hours, etc.).
    - Creates the file if it doesn't exist.
    - Updates the file if it exists (merges and removes duplicates).
    """
    
    if not new_places_list:
        print("⚠️ No data to register.")
        return

    # 1. Convert new data to DataFrame
    # We use json_normalize to slightly flatten the structure 
    # (e.g., it separates geometry.location.lat automatically), 
    # but keeps lists like 'photos' as raw strings.
    df_new = pd.json_normalize(new_places_list)

    # 2. Check if the CSV already exists
    if os.path.exists(filename):
        try:
            # Load existing data
            df_old = pd.read_csv(filename)
            
            # 3. Concatenate (Merge old + new)
            # sort=False prevents columns from being reordered alphabetically
            df_combined = pd.concat([df_old, df_new], sort=False)
            
        except pd.errors.EmptyDataError:
            # If file exists but is empty
            df_combined = df_new
    else:
        # File doesn't exist yet
        print(f"🆕 Creating new dataset: {filename}")
        df_combined = df_new

    # 4. Deduplicate
    # We remove rows that have the same 'place_id'
    # keep='last' ensures we always have the freshest data from Google
    if 'place_id' in df_combined.columns:
        before_count = len(df_combined)
        df_combined = df_combined.drop_duplicates(subset='place_id', keep='last')
        after_count = len(df_combined)
        
        if before_count > after_count:
            print(f"♻️  Updated existing entries (Removed {before_count - after_count} duplicates).")

    # 5. Save to CSV
    # index=False removes the row numbers (0, 1, 2...) from the file
    df_combined.to_csv(filename, index=False, encoding='utf-8')
    
    print(f"✅ Success! Database now contains {len(df_combined)} unique places.")

# --- ADD THIS TO THE END OF utils.py ---

def get_box_radius(min_lat, min_lng, max_lat, max_lng):
    """
    Calculates the distance from the center of the box to a corner in meters.
    Used to set the 'radius' parameter for Google Places API.
    """
    center_lat = (min_lat + max_lat) / 2
    center_lng = (min_lng + max_lng) / 2
    
    # Haversine formula approximation for radius
    R = 6371000  # Earth radius in meters
    d_lat = math.radians(max_lat - center_lat)
    d_lng = math.radians(max_lng - center_lng)
    
    a = (math.sin(d_lat / 2) * math.sin(d_lat / 2) +
         math.cos(math.radians(center_lat)) * math.cos(math.radians(max_lat)) *
         math.sin(d_lng / 2) * math.sin(d_lng / 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def subdivide_box(min_lat, min_lng, max_lat, max_lng):
    """
    Splits a bounding box into 4 smaller sub-quadrants.
    Returns a list of tuples: (min_lat, min_lng, max_lat, max_lng)
    """
    mid_lat = (min_lat + max_lat) / 2
    mid_lng = (min_lng + max_lng) / 2
    
    return [
        (min_lat, min_lng, mid_lat, mid_lng),  # Bottom Left
        (min_lat, mid_lng, mid_lat, max_lng),  # Bottom Right
        (mid_lat, min_lng, max_lat, mid_lng),  # Top Left
        (mid_lat, mid_lng, max_lat, max_lng)   # Top Right
    ]