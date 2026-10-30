import os
import re
import json
import asyncio
import urllib.parse
import cloudscraper
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from asgiref.sync import sync_to_async
from django.db.models import Q
from django.core.management.base import BaseCommand
from anime.models import AnimeEpisode
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ==========================================
# CONFIGURATIONS
# ==========================================
WP_SITE_URL = os.getenv("WP_SITE_URL", "https://anikototv.net").rstrip('/')
WP_USERNAME = os.getenv("WP_USERNAME", "admin")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")

# OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if (OPENAI_API_KEY and not OPENAI_API_KEY.startswith("sk-proj-YOUR")) else None

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

@sync_to_async
def episode_exists_in_local_db(page_url, series_name=None, ep_num=None):
    """Check if the episode already exists in the local Django database."""
    if AnimeEpisode.objects.filter(source_url=page_url).exists():
        return True
    if series_name and ep_num:
        pattern = f"{series_name} Episode {ep_num}"
        if AnimeEpisode.objects.filter(title__icontains=pattern).exists():
            return True
    return False

@sync_to_async
def save_episode_to_db(page_url, title, image_url, found_stream_urls):
    """Save the episode details to local Django DB."""
    episode_obj, created = AnimeEpisode.objects.get_or_create(
        source_url=page_url,
        defaults={
            'title': title,
            'thumbnail': image_url,
            'stream_urls': found_stream_urls,
            'is_published': True
        }
    )
    return episode_obj.id, created

def clean_series_name(raw_name):
    """Clean extra prefixes and suffixes from series name."""
    name = re.sub(r'^(Watch\s+|Free!\s+|Ver\s+)+', '', raw_name, flags=re.IGNORECASE)
    name = re.sub(r'\s+Online.*$', '', name, flags=re.IGNORECASE)
    name = name.strip()
    return name

def regex_fallback_parse(page_url, page_title=""):
    """Fallback parser to extract clean series name, episode number, and subbed status."""
    series_name = ""
    ep_num = "1"
    subbed_status = "Sub"

    if page_title:
        m = re.search(r'Watch\s+(.*?)\s+Episode\s+(\d+)', page_title, re.IGNORECASE)
        if m:
            series_name = clean_series_name(m.group(1))
            ep_num = m.group(2).strip()
        if 'dub' in page_title.lower() and 'sub' not in page_title.lower():
            subbed_status = "Dub"

    if not series_name:
        slug = page_url.split('/watch/')[-1].strip('/')
        parts = slug.split('/')
        base_slug = parts[0]
        if len(parts) > 1 and 'ep-' in parts[1]:
            ep_num = parts[1].replace('ep-', '')

        slug_parts = base_slug.split('-')
        if len(slug_parts[-1]) == 5 and slug_parts[-1].isalnum():
            slug_parts.pop()
        series_name = clean_series_name(" ".join(slug_parts).title())

    sub_suffix = "English Subbed" if subbed_status == "Sub" else "English Dubbed"
    full_title = f"{series_name} Episode {ep_num} {sub_suffix}"

    return {
        "full_title": full_title,
        "series_name": series_name,
        "episode_number": ep_num,
        "subbed_status": subbed_status,
        "seo_title": f"Watch {full_title} Online HD - Anikoto",
        "seo_desc": f"Watch {full_title} online in HD quality on Anikoto."
    }

def ai_agent_extract_metadata(raw_url, page_title=""):
    """OpenAI Agent to generate refined metadata with automatic fallback."""
    fallback_data = regex_fallback_parse(raw_url, page_title)

    if not openai_client:
        return fallback_data

    prompt = f"""
    Analyze this anime episode:
    URL: {raw_url}
    Page Title: {page_title}
    Suggested Series: {fallback_data['series_name']}
    Suggested Episode: {fallback_data['episode_number']}

    Generate a clean JSON object with exact keys:
    - "series_name": Clean official series name (e.g. "Bleach: Thousand-Year Blood War - The Calamity")
    - "episode_number": Just the numeric episode string (e.g. "10")
    - "subbed_status": "Sub" or "Dub"
    - "full_title": In format "{{series_name}} Episode {{episode_number}} English Subbed" (or "English Dubbed")
    - "seo_title": SEO title e.g. "Watch {{full_title}} Online HD - Anikoto"
    - "seo_desc": SEO meta description e.g. "Watch {{full_title}} online in HD quality on Anikoto."

    Return ONLY valid JSON.
    """

    try:
        chat_completion = openai_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are an automated anime metadata JSON generator. Respond strictly in JSON format."},
                {"role": "user", "content": prompt}
            ],
            model="gpt-4o-mini",
            response_format={"type": "json_object"}
        )
        data = json.loads(chat_completion.choices[0].message.content)
        sub_word = "English Subbed" if data.get('subbed_status') == 'Sub' else "English Dubbed"
        if not data.get('full_title') or sub_word not in data['full_title']:
            data['full_title'] = f"{data.get('series_name', fallback_data['series_name'])} Episode {data.get('episode_number', fallback_data['episode_number'])} {sub_word}"
        return data
    except Exception as e:
        print(f"[OPENAI AGENT NOTICE] {e} -> Using Fallback Parser")
        return fallback_data

def is_duplicate_on_wordpress(series_name, ep_num, full_title):
    """
    Check if the episode already exists on the WordPress site.
    Checks:
    1. Direct post slug matching
    2. Any existing post under the series category matching episode number
    """
    auth = (WP_USERNAME, WP_APP_PASSWORD)

    # 1. Check by Post Slug
    candidate_slug = re.sub(r'[^a-zA-Z0-9]+', '-', full_title.lower()).strip('-')
    try:
        r_slug = requests.get(f"{WP_SITE_URL.rstrip('/')}/wp-json/wp/v2/posts?slug={candidate_slug}", auth=auth, timeout=10)
        if r_slug.status_code == 200 and r_slug.json():
            existing = r_slug.json()[0]
            return True, f"Found on WP by slug '{candidate_slug}' (Post ID: {existing['id']})"
    except Exception as e:
        print(f"[WP DUPLICATE CHECK ERROR (Slug)] {e}")

    # 2. Check by Series Category and Episode Number
    try:
        search_q = urllib.parse.quote(series_name)
        r_cat = requests.get(f"{WP_SITE_URL.rstrip('/')}/wp-json/wp/v2/categories?search={search_q}", auth=auth, timeout=10)
        if r_cat.status_code == 200 and r_cat.json():
            cat_id = r_cat.json()[0]['id']
            r_posts = requests.get(f"{WP_SITE_URL.rstrip('/')}/wp-json/wp/v2/posts?categories={cat_id}&per_page=50", auth=auth, timeout=10)
            if r_posts.status_code == 200:
                for p in r_posts.json():
                    p_ep = str(p.get('meta_box', {}).get('ero_episodebaru', '')).strip()
                    p_title = p.get('title', {}).get('rendered', '')
                    # Exact episode number in meta_box
                    if p_ep == str(ep_num):
                        return True, f"Found on WP in Category {cat_id} (Post ID: {p['id']}, Title: '{p_title}')"
                    # Episode number in title
                    m = re.search(r'Episode\s+(\d+)', p_title, re.IGNORECASE)
                    if m and m.group(1) == str(ep_num):
                        return True, f"Found on WP in Category {cat_id} by title (Post ID: {p['id']}, Title: '{p_title}')"
    except Exception as e:
        print(f"[WP DUPLICATE CHECK ERROR (Category)] {e}")

    return False, None

def get_or_create_sub_category(series_name):
    """
    Find or create WordPress Category for this anime series.
    """
    auth = (WP_USERNAME, WP_APP_PASSWORD)
    try:
        search_q = urllib.parse.quote(series_name)
        r = requests.get(f"{WP_SITE_URL.rstrip('/')}/wp-json/wp/v2/categories?search={search_q}", auth=auth, timeout=10)
        if r.status_code == 200:
            for cat in r.json():
                if cat['name'].lower() == series_name.lower():
                    return cat['id']
            if r.json():
                return r.json()[0]['id']

        # Create new category for series
        r_create = requests.post(
            f"{WP_SITE_URL.rstrip('/')}/wp-json/wp/v2/categories",
            auth=auth,
            json={'name': series_name},
            timeout=10
        )
        if r_create.status_code in [200, 201]:
            new_id = r_create.json().get('id')
            print(f"[+] Created new Category '{series_name}' (ID: {new_id})")
            return new_id
    except Exception as e:
        print(f"[WP CATEGORY ERROR] {e}")

    return 1

def find_wp_series_post_id(series_name):
    """Search for the parent Series post ID for 'ero_seri' meta field."""
    auth = (WP_USERNAME, WP_APP_PASSWORD)
    try:
        first_words = " ".join(series_name.split()[:4])
        search_q = urllib.parse.quote(first_words)
        r = requests.get(f"{WP_SITE_URL.rstrip('/')}/wp-json/wp/v2/search?search={search_q}", auth=auth, timeout=10)
        if r.status_code == 200:
            for item in r.json():
                if item.get('subtype') == 'series':
                    return item.get('id')
    except Exception as e:
        print(f"[WP SERIES SEARCH ERROR] {e}")
    return ""

def upload_featured_image(image_url, title):
    """Upload thumbnail image to WordPress Media Library."""
    if not image_url:
        return None
    try:
        img_resp = requests.get(image_url, timeout=15)
        if img_resp.status_code == 200:
            clean_filename = re.sub(r'[^a-zA-Z0-9]+', '-', title.lower()).strip('-') + ".jpg"
            headers = {
                'Content-Type': 'image/jpeg',
                'Content-Disposition': f'attachment; filename="{clean_filename}"'
            }
            res = requests.post(
                f"{WP_SITE_URL.rstrip('/')}/wp-json/wp/v2/media",
                headers=headers,
                data=img_resp.content,
                auth=(WP_USERNAME, WP_APP_PASSWORD),
                timeout=25
            )
            if res.status_code in [200, 201]:
                return res.json().get('id')
    except Exception as e:
        print(f"[WP MEDIA ERROR] {e}")
    return None

def publish_to_wordpress(ai_data, thumbnail, stream_servers, source_url):
    """Publish to WordPress strictly under Series Category with Meta Box fields."""
    api_url = f"{WP_SITE_URL.rstrip('/')}/wp-json/wp/v2/posts"
    auth = (WP_USERNAME, WP_APP_PASSWORD)

    # 1. Upload thumbnail
    featured_media_id = upload_featured_image(thumbnail, ai_data['full_title'])

    # 2. Get Category for this Anime Series
    series_name = ai_data.get('series_name', '')
    series_cat_id = get_or_create_sub_category(series_name)
    categories = [series_cat_id]

    # 3. Find parent series post ID for DramaStream 'ero_seri' field
    series_post_id = find_wp_series_post_id(series_name)

    # 4. Build Embed Video data for DramaStream Theme
    ab_embedgroup = []
    ero_embed_list = []
    for s in stream_servers:
        server_name = s.get('name', 'MegaPlay')
        stream_url = s.get('url', '')
        if stream_url:
            embed_code = f'<iframe src="{stream_url}" width="100%" height="450" frameborder="0" allowfullscreen></iframe>' if not stream_url.startswith('<iframe') else stream_url
            ab_embedgroup.append({
                'ab_hostname': server_name,
                'ab_embed': embed_code
            })
            ero_embed_list.append(stream_url)

    if not ab_embedgroup:
        ab_embedgroup.append({
            'ab_hostname': 'MegaPlay',
            'ab_embed': ''
        })

    ep_num = str(ai_data.get('episode_number', '1'))
    sub_status = ai_data.get('subbed_status', 'Sub')

    # Meta Box custom fields for DramaStream theme
    meta_box_data = {
        'ero_subepisode': sub_status,
        'ero_episodebaru': ep_num,
        'ero_episodetitle': f"Episode {ep_num}",
        'ero_download': '',
        'ero_seri': str(series_post_id) if series_post_id else '',
        'ero_multipart': 'no',
        'ab_embedgroup': ab_embedgroup,
        'ero_embed': ero_embed_list,
        'ab_downloadgroup_ep': []
    }

    payload = {
        'title': ai_data['full_title'],
        'status': 'publish',
        'content': '',
        'categories': categories,
        'meta_box': meta_box_data,
        'meta': {
            '_yoast_wpseo_title': ai_data.get('seo_title'),
            '_yoast_wpseo_metadesc': ai_data.get('seo_desc'),
            '_yoast_wpseo_focuskw': ai_data.get('full_title')
        }
    }

    if featured_media_id:
        payload['featured_media'] = featured_media_id

    try:
        response = requests.post(
            api_url,
            json=payload,
            auth=auth,
            timeout=45
        )
        if response.status_code in [200, 201]:
            post_id = response.json().get('id')
            post_link = response.json().get('link', '')
            print(f"[WP PUBLISHED SUCCESS] Post ID: {post_id} | Title: {ai_data['full_title']}")
            print(f"   -> Link: {post_link}")
            print(f"   -> Category ID: {series_cat_id} ({series_name})")
            print(f"   -> Series ID: {series_post_id}")
            print(f"   -> Servers Added ({len(ab_embedgroup)}): {[s['ab_hostname'] for s in ab_embedgroup]}")
            return True
        else:
            print(f"[WP ERROR] Failed ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"[WP EXCEPTION] {e}")
        return False

def fetch_latest_episodes_from_home():
    """Scrape homepage and latest-updated pages to collect episode links."""
    base_url = "https://anikototv.to"
    target_urls = [
        "https://anikototv.to/home",
        "https://anikototv.to/latest-updated?page=1",
        "https://anikototv.to/latest-updated?page=2"
    ]

    episode_links = []
    for page_url in target_urls:
        try:
            response = scraper.get(page_url, timeout=15)
            if response.status_code != 200:
                continue
            soup = BeautifulSoup(response.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/watch/' in href and ('/ep-' in href or 'ep-' in href):
                    full_url = urljoin(base_url, href)
                    if full_url not in episode_links:
                        episode_links.append(full_url)
        except Exception as e:
            print(f"Error fetching {page_url}: {e}")

    return episode_links

def extract_episode_data(page_url):
    """Extract anime metadata and all mirror stream links from anikototv."""
    try:
        headers = {'Referer': 'https://anikototv.to/home'}
        r = scraper.get(page_url, headers=headers, timeout=20)
        if r.status_code != 200:
            print(f"Failed to load {page_url} (Status: {r.status_code})")
            return None

        soup = BeautifulSoup(r.text, 'html.parser')
        og_title = soup.find('meta', property='og:title')
        page_title = og_title['content'] if og_title else (soup.title.string if soup.title else '')

        og_image = soup.find('meta', property='og:image')
        image_url = og_image['content'] if og_image else ''

        # Extract structured metadata
        ai_data = ai_agent_extract_metadata(page_url, page_title)

        # Get anime ID to query server streams
        watch_main = soup.find('div', id='watch-main') or soup.find(attrs={'data-id': True})
        anime_id = watch_main.get('data-id') if watch_main else None
        ep_num = ai_data.get('episode_number', '1')

        stream_servers = []
        if anime_id:
            ep_list_url = f"https://anikototv.to/ajax/episode/list/{anime_id}"
            ajax_headers = {'X-Requested-With': 'XMLHttpRequest', 'Referer': page_url}
            r_ep = scraper.get(ep_list_url, headers=ajax_headers, timeout=15)
            if r_ep.status_code == 200:
                ep_data = r_ep.json()
                ep_soup = BeautifulSoup(ep_data.get('result', ''), 'html.parser')
                ep_link = ep_soup.find('a', attrs={'data-num': ep_num}) or ep_soup.find('a', attrs={'data-slug': ep_num})
                if not ep_link and ep_soup.find_all('a'):
                    ep_link = ep_soup.find_all('a')[-1]

                if ep_link and ep_link.get('data-ids'):
                    servers_url = f"https://anikototv.to/ajax/server/list?servers={urllib.parse.quote(ep_link.get('data-ids'))}"
                    r_srv = scraper.get(servers_url, headers=ajax_headers, timeout=15)
                    if r_srv.status_code == 200:
                        srv_soup = BeautifulSoup(r_srv.json().get('result', ''), 'html.parser')
                        seen_urls = set()
                        for li in srv_soup.find_all('li', attrs={'data-link-id': True}):
                            raw_srv_name = li.get_text(strip=True)
                            parent_type = li.find_parent('div', class_='type')
                            type_label = parent_type.get('data-type', '').upper() if parent_type else ''
                            srv_name = f"{raw_srv_name} ({type_label})" if type_label else raw_srv_name

                            link_id = li['data-link-id']
                            srv_src_url = f"https://anikototv.to/ajax/server?get={urllib.parse.quote(link_id)}"
                            r_src = scraper.get(srv_src_url, headers=ajax_headers, timeout=15)
                            if r_src.status_code == 200:
                                url_val = r_src.json().get('result', {}).get('url')
                                if url_val and url_val not in seen_urls:
                                    seen_urls.add(url_val)
                                    if '/dub' in url_val.lower():
                                        ai_data['subbed_status'] = 'Dub'
                                    stream_servers.append({'name': srv_name, 'url': url_val})

        # Update full title with accurate subbed_status
        sub_word = "English Subbed" if ai_data.get('subbed_status') == 'Sub' else "English Dubbed"
        ai_data['full_title'] = f"{ai_data['series_name']} Episode {ai_data['episode_number']} {sub_word}"

        return {
            'ai_data': ai_data,
            'image_url': image_url,
            'streams': stream_servers
        }
    except Exception as e:
        print(f"Error extracting {page_url}: {e}")
        return None

async def process_episode(page_url):
    """Process single episode with strict double-layer duplicate check (Local DB + Live WP)."""
    # 1. Quick local DB check by URL
    if await episode_exists_in_local_db(page_url):
        print(f"[SKIP - IN LOCAL DB] Already ingested: {page_url}")
        return False

    print(f"\n[+] Extracting Metadata: {page_url}")
    ep_data = extract_episode_data(page_url)
    if not ep_data:
        print(f"[FAILED] Could not extract details for {page_url}")
        return False

    ai_data = ep_data['ai_data']
    series_name = ai_data['series_name']
    ep_num = ai_data['episode_number']
    full_title = ai_data['full_title']

    # 2. Local DB check by Series + Episode in Title
    if await episode_exists_in_local_db(page_url, series_name=series_name, ep_num=ep_num):
        print(f"[SKIP - LOCAL DB DUPLICATE] '{full_title}' already recorded in database.")
        return False

    # 3. Live WordPress Verification on anikototv.net
    is_dup, reason = is_duplicate_on_wordpress(series_name, ep_num, full_title)
    if is_dup:
        print(f"[SKIP - ALREADY ON WORDPRESS] {reason}")
        # Sync to local DB so future runs skip it immediately
        await save_episode_to_db(page_url, full_title, ep_data['image_url'], [s['url'] for s in ep_data['streams']])
        return False

    image_url = ep_data['image_url']
    streams = ep_data['streams']
    stream_urls = [s['url'] for s in streams]

    # Save to local Django DB
    ep_id, created = await save_episode_to_db(page_url, full_title, image_url, stream_urls)

    if created:
        print(f"[DB SAVED] ID: {ep_id} | Title: {full_title}")
        # Publish to anikototv.net
        published = publish_to_wordpress(ai_data, image_url, streams, page_url)
        return published

    return False

async def run_scraper_pipeline(limit=10):
    """Main pipeline loop to fetch links and process up to `limit` new episodes sequentially."""
    links = fetch_latest_episodes_from_home()
    if not links:
        print("No episode links found.")
        return

    print(f"Found {len(links)} episode links. Target new episodes to process: {limit}...")
    processed_count = 0
    for link in links:
        if processed_count >= limit:
            break

        was_published = await process_episode(link)
        if was_published:
            processed_count += 1

class Command(BaseCommand):
    help = "Automated scraper powered by AI Agent to publish episodes to WordPress (anikototv.net)"

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=10, help='Number of new episodes to scrape')

    def handle(self, *args, **options):
        limit = options['limit']
        self.stdout.write(self.style.SUCCESS(f"Starting Scraper & Publisher for anikototv.net (Limit: {limit})..."))
        asyncio.run(run_scraper_pipeline(limit=limit))
        self.stdout.write(self.style.SUCCESS("Scraping completed!"))
