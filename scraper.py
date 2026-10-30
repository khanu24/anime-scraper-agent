import os
import django
import asyncio
import urllib.parse
import re
import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from asgiref.sync import sync_to_async

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from anime.models import AnimeEpisode

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

@sync_to_async
def episode_exists_in_db(page_url):
    return AnimeEpisode.objects.filter(source_url=page_url).exists()

@sync_to_async
def save_episode_to_db(page_url, title, image_url, found_stream_urls):
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

def fetch_latest_episodes_from_home():
    home_url = "https://anikototv.to/home"
    base_url = "https://anikototv.to"

    print(f"\n[1] Fetching dynamic homepage links from {home_url}...")
    try:
        response = scraper.get(home_url, timeout=15)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        episode_links = []

        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/watch/' in href and ('/ep-' in href or 'ep-' in href):
                full_url = urljoin(base_url, href)
                if full_url not in episode_links:
                    episode_links.append(full_url)

        print(f"[+] Total dynamic episode links found: {len(episode_links)}")
        return episode_links
    except Exception as e:
        print(f"Error fetching homepage: {e}")
        return []

def extract_episode_data(page_url):
    try:
        headers = {'Referer': 'https://anikototv.to/home'}
        r = scraper.get(page_url, headers=headers, timeout=20)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, 'html.parser')
        og_title = soup.find('meta', property='og:title')
        page_title = og_title['content'] if og_title else (soup.title.string if soup.title else '')

        # Clean title
        m = re.search(r'Watch\s+(.*?)\s+Episode\s+(\d+)', page_title, re.IGNORECASE)
        if m:
            series_name = re.sub(r'^(Free!\s+|Ver\s+)', '', m.group(1)).strip()
            ep_num = m.group(2).strip()
        else:
            slug = page_url.split('/watch/')[-1].strip('/')
            parts = slug.split('/')
            series_name = parts[0].rsplit('-', 1)[0].replace('-', ' ').title()
            ep_num = parts[1].replace('ep-', '') if len(parts) > 1 else '1'

        sub_suffix = "English Subbed"
        full_title = f"{series_name} Episode {ep_num} {sub_suffix}"

        og_image = soup.find('meta', property='og:image')
        image_url = og_image['content'] if og_image else ''

        watch_main = soup.find('div', id='watch-main') or soup.find(attrs={'data-id': True})
        anime_id = watch_main.get('data-id') if watch_main else None

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
                        for li in srv_soup.find_all('li', attrs={'data-link-id': True}):
                            link_id = li['data-link-id']
                            srv_src_url = f"https://anikototv.to/ajax/server?get={urllib.parse.quote(link_id)}"
                            r_src = scraper.get(srv_src_url, headers=ajax_headers, timeout=15)
                            if r_src.status_code == 200:
                                url_val = r_src.json().get('result', {}).get('url')
                                if url_val:
                                    stream_servers.append(url_val)

        return {
            'title': full_title,
            'image_url': image_url,
            'streams': stream_servers
        }
    except Exception as e:
        print(f"Error scraping {page_url}: {e}")
        return None

async def main():
    links = fetch_latest_episodes_from_home()
    if not links:
        return

    print("\n[2] Processing episodes...")
    for link in links[:3]:
        exists = await episode_exists_in_db(link)
        if exists:
            print(f"[SKIP] Already exists in DB: {link}")
            continue

        data = extract_episode_data(link)
        if data:
            ep_id, created = await save_episode_to_db(link, data['title'], data['image_url'], data['streams'])
            if created:
                print(f"[SUCCESS] Saved to Database -> ID: {ep_id} | Title: {data['title']} | Streams: {len(data['streams'])}")

if __name__ == "__main__":
    asyncio.run(main())
