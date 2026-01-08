# 🗺️ Google Place Extractor

A powerful **Google Places scraper** with a real-time interactive map interface. Extract business data from **anywhere in the world** using an adaptive grid system that automatically handles dense areas.

![Screenshot](screenshot.png?v=2)

## ✨ Features

- **🌍 Worldwide Coverage** – Works in any country, any city
- **🗺️ Interactive Map** – Click to position your search grid anywhere
- **📍 Preset Locations** – Quick access to major cities (Paris, New York, London, Tokyo, etc.)
- **🔄 Adaptive Grid System** – Automatically subdivides dense areas to capture all results
- **⚡ Parallel Processing** – Multi-threaded API calls with configurable RPS
- **📊 Live Progress** – Real-time visualization of processed zones and found places
- **💾 CSV Export** – Save results with full Google Places data

## 🚀 Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/Blurenis/Google_Place_Extractor.git
cd Google_Place_Extractor
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure your API key
Create a `.env` file:
```env
GOOGLE_KEY=your_google_places_api_key
```

### 4. Run the app
```bash
streamlit run main.py
```

## 📋 Usage

1. **Select a location** – Choose a preset city or click anywhere on the map
2. **Set parameters** – Configure keyword, grid size, and request speed
3. **Start scraping** – Use "Pas à Pas" for batch mode or enable "Auto-Run" for continuous scraping
4. **Export data** – Click "Sauvegarder" to export results to CSV

## ⚙️ Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| **Mot-clé** | Search keyword (e.g., "restaurant", "dentist") | `infirmier libéral` |
| **Rayon Min** | Minimum search radius in meters | `100` |
| **Requêtes/Seconde** | API calls per batch | `2` |
| **Taille Grille** | Initial grid size (N × 70km blocks) | `3` |

## 📁 Project Structure

```
├── main.py          # Streamlit app & scraping logic
├── utils.py         # API calls, geometry helpers, CSV handling
├── .env             # API key configuration (create this)
├── requirements.txt # Python dependencies
└── README.md
```

## 🔧 How It Works

1. **Grid Generation** – Creates an N×N grid of 70km blocks centered on your selected location
2. **Smart Subdivision** – If a zone returns 20+ results (API limit), it splits into 4 sub-quadrants
3. **Dense Area Handling** – For small zones still hitting 20+ results, fetches up to 3 pages (60 results max)
4. **Deduplication** – Results are deduplicated by `place_id` when saved

## 📊 Output Format

The CSV export includes:
- `name` – Business name
- `place_id` – Unique Google identifier
- `formatted_address` – Full address
- `geometry.location.lat/lng` – Coordinates
- `rating` – Average rating
- `user_ratings_total` – Number of reviews
- `types` – Business categories
- And more...

## ⚠️ Important Notes

- **API Costs** – Google Places API has costs. Monitor your usage in Google Cloud Console.
- **Rate Limiting** – Default 2 RPS is conservative. Increase carefully to avoid quota issues.
- **Terms of Service** – Ensure compliance with Google's ToS for your use case.

## 🛠️ Requirements

- Python 3.8+
- Google Cloud account with Places API enabled
- Valid API key with billing configured

## 📄 License

MIT License – Free to use and modify.

---

Made with ❤️ using [Streamlit](https://streamlit.io/) & [Folium](https://python-visualization.github.io/folium/)

