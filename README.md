# Anime Scraper & Auto-Poster Agent 🎬🚀

An intelligent, automated anime scraper and publishing engine built with Python, Django, Cloudscraper, Playwright, and OpenAI. It automatically extracts latest anime episodes, retrieves multiple high-speed video streaming mirrors (SUB & DUB), and publishes them directly to your WordPress streaming website (supporting themes like DramaStream / Themesia) with zero duplicates.

---

## ✨ Features

- **Automated Scraping**: Scrapes latest anime episodes from dynamic sources with anti-bot bypass (`cloudscraper` + `playwright`).
- **Multi-Server Stream Resolving**: Resolves direct iframe embed links and multi-server mirrors (HD-1, Vidstream, MegaPlay, etc.) for both SUB and DUB audio.
- **Smart Metadata Extraction**: Uses OpenAI (`gpt-4o-mini`) to extract clean titles, episode numbers, and SEO metadata with an automatic regex-based fallback.
- **Multi-Layer Duplicate Prevention**:
  1. Local Database URL check
  2. Local Database Title & Episode number check
  3. Live WordPress remote check (by Post Slug and Category Episode Meta Box)
- **Automatic WordPress Category Management**: Assigns episodes to their respective series category, automatically creating sub-categories under the parent Anime category if missing.
- **Custom Meta Box Integration**: Automatically populates Theme Meta Box fields (`ero_subepisode`, `ero_episodebaru`, `ero_episodetitle`, `ero_seri`, and `ab_embedgroup` for embedded video players).
- **REST API & Admin Panel**: Built on Django with Django REST Framework providing an endpoint for ingested episodes.

---

## 📁 Project Structure

```text
anime-scraper-agent/
├── anime/                          # Django App
│   ├── management/commands/
│   │   └── run_scraper.py         # Main automated scraper & publisher command
│   ├── models.py                  # AnimeEpisode model
│   ├── serializers.py             # DRF serializers
│   ├── views.py                   # API views
│   └── urls.py                    # App endpoints
├── core/                           # Django Project settings & routing
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── scraper.py                      # Standalone scraper script
├── test_scraper.py                 # Playwright inspection utility
├── manage.py                       # Django management script
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variable template
├── .gitignore                      # Git ignored files & patterns
└── README.md                       # Documentation
```

---

## 🛠️ Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/khanu24/anime-scraper-agent.git
cd anime-scraper-agent
```

### 2. Create and Activate Virtual Environment
```bash
# macOS/Linux
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Open `.env` and fill in your credentials:
```env
# WordPress REST API Configuration
WP_SITE_URL=https://your-wordpress-site.com
WP_USERNAME=admin
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx

# OpenAI API Key for Metadata Extraction
OPENAI_API_KEY=sk-proj-your-openai-api-key

# Optional Groq API Key
GROQ_API_KEY=
```

> **Note**: For WordPress, generate an **Application Password** from `wp-admin` > **Users** > **Profile** > **Application Passwords**. Ensure the **MB Rest API** plugin is installed and active on your WordPress site so Meta Box fields can be updated via the REST API.

### 5. Apply Database Migrations
```bash
python manage.py migrate
```

---

## 🚀 Usage

### Run Automated Scraper & Publisher Command
Run the scraper and specify how many new episodes to process:
```bash
# Process top 10 new episodes
python manage.py run_scraper --limit 10

# Process top 25 new episodes
python manage.py run_scraper --limit 25
```

### Run Standalone Scraper (Local DB only)
```bash
python scraper.py
```

### Run Playwright DOM/Stream Inspector
```bash
python test_scraper.py
```

### Start Local Django Server & API
```bash
python manage.py runserver
```
Access the REST API at `http://127.0.0.1:8000/api/episodes/`.

---

## 🛡️ Security

- Credentials, API keys, and sensitive tokens are strictly kept out of version control via `.env` and `.gitignore`.
- Always keep your `.env` private and never commit it to public repositories.

---

## 📄 License
This project is open-source under the MIT License.
