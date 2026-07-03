import json
from datetime import datetime, timezone
from pathlib import Path

import bs4
import requests

GUIDES = [
    {
        'url': 'https://steamcommunity.com/sharedfiles/filedetails/?id=3476068089', 
        'owner_id': '76561198840412181',
        'file_id': '3476068089',
        'output': 'comments_1.json',
    },
    {
        'url': 'https://steamcommunity.com/sharedfiles/filedetails/?id=3438530146',
        'owner_id': '76561199112392013',
        'file_id': '3438530146',
        'output': 'comments_2.json',
    },
    {
        'url': 'https://steamcommunity.com/sharedfiles/filedetails/?id=3478574794',
        'owner_id': '76561199112392013',
        'file_id': '3478574794',
        'output': 'comments_3.json',
    },
    {
        'url': 'https://steamcommunity.com/sharedfiles/filedetails/?id=3478642806',
        'owner_id': '76561198840412181',
        'file_id': '3478642806',
        'output': 'comments_4.json',
    },
]

REQUEST_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/126.0.0.0 Safari/537.36'
    )
}
OUTPUT_DIR = Path('docs')


def normalize_avatar_url(avatar_url):
    if not avatar_url:
        return None
    if 'steamstatic.com' in avatar_url and '_medium' not in avatar_url and avatar_url.endswith('.jpg'):
        return avatar_url.replace('.jpg', '_medium.jpg')
    return avatar_url


def parse_timestamp(comment_node):
    timestamp_node = comment_node.find(attrs={'data-timestamp': True})
    if timestamp_node:
        unix_timestamp = int(timestamp_node['data-timestamp'])
        return datetime.fromtimestamp(unix_timestamp, tz=timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def extract_comments_from_html(html_text):
    comments = []
    soup = bs4.BeautifulSoup(html_text, 'html.parser')

    for single_comment in soup.select('.commentthread_comment.responsive_body_text'):
        try:
            avatar_tag = single_comment.select_one('.commentthread_comment_avatar img')
            author_tag = single_comment.find('bdi')
            message_tag = single_comment.select_one('.commentthread_comment_text')

            if not author_tag or not message_tag:
                continue

            comments.append({
                'author': author_tag.get_text(strip=True),
                'avatar': normalize_avatar_url(avatar_tag.get('src') if avatar_tag else None),
                'timestamp': parse_timestamp(single_comment),
                'comment': message_tag.get_text(strip=True),
            })
        except Exception as error:
            print(f'Error processing comment: {error}')

    return comments


def fetch_live_comments(guide):
    api_url = (
        'https://steamcommunity.com/comment/PublishedFile_Public/render/'
        f"{guide['owner_id']}/{guide['file_id']}/"
    )
    start = 0
    page_size = 100
    total_count = None
    comments = []

    while total_count is None or start < total_count:
        response = requests.get(
            api_url,
            params={'count': page_size, 'start': start, 'totalcount': start},
            headers=REQUEST_HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        html_chunk = payload.get('comments_html', '')
        comments.extend(extract_comments_from_html(html_chunk))

        total_count = payload.get('total_count', 0)
        start += page_size

        if not html_chunk.strip():
            break

    return comments


def load_existing_comments(filename):
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        return []

    with file_path.open('r', encoding='utf-8') as file:
        data = json.load(file)
        return data.get('comments', [])


def merge_comments(existing_comments, live_comments):
    merged = {}

    for comment in existing_comments + live_comments:
        key = (
            comment.get('author', '').strip(),
            comment.get('comment', '').strip(),
            comment.get('timestamp', '').strip(),
        )
        if key not in merged:
            merged[key] = {
                'author': comment.get('author'),
                'avatar': comment.get('avatar'),
                'timestamp': comment.get('timestamp'),
                'comment': comment.get('comment'),
            }
        elif not merged[key].get('avatar') and comment.get('avatar'):
            merged[key]['avatar'] = comment.get('avatar')

    return sorted(
        merged.values(),
        key=lambda comment: comment.get('timestamp', ''),
        reverse=True,
    )


def save_comments_to_json(comments, filename):
    OUTPUT_DIR.mkdir(exist_ok=True)
    file_path = OUTPUT_DIR / filename

    with file_path.open('w', encoding='utf-8') as file:
        json.dump({'comments': comments}, file, ensure_ascii=False, indent=2)


def main():
    for guide in GUIDES:
        try:
            print(f"Procesando {guide['url']}")
            live_comments = fetch_live_comments(guide)
            existing_comments = load_existing_comments(guide['output'])
            merged_comments = merge_comments(existing_comments, live_comments)
            save_comments_to_json(merged_comments, guide['output'])
            print(
                f"Comentarios guardados en {guide['output']} "
                f"(nuevos visibles: {len(live_comments)}, total acumulado: {len(merged_comments)})"
            )
        except Exception as error:
            print(f"Error al procesar {guide['url']}: {error}")


if __name__ == '__main__':
    main()
