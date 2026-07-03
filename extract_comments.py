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


def is_real_avatar_url(url):
    if not url:
        return False

    url = url.strip().lower()

    real_avatar_markers = [
        'avatars.akamai.steamstatic.com',
        'avatars.steamstatic.com',
        'steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars',
        '/steamcommunity/public/images/avatars/',
        '/avatars/',
    ]

    fake_or_frame_markers = [
        'profile_frame',
        'profileframe',
        'avatar_frame',
        'avatarframe',
        'animated_avatar',
        'miniprofile',
        'economy/image',
        'items/',
        'communityitems',
        'border',
        'frame',
    ]

    if any(marker in url for marker in fake_or_frame_markers):
        return False

    return any(marker in url for marker in real_avatar_markers)


def extract_urls_from_srcset(srcset_value):
    if not srcset_value:
        return []

    urls = []
    for item in srcset_value.split(','):
        item = item.strip()
        if not item:
            continue
        urls.append(item.split()[0])

    return urls


def get_candidate_urls(tag):
    if not tag:
        return []

    candidates = []

    for attr in ['src', 'data-src', 'data-original']:
        value = tag.get(attr)
        if value:
            candidates.append(value)

    for attr in ['srcset', 'data-srcset']:
        value = tag.get(attr)
        candidates.extend(extract_urls_from_srcset(value))

    return [candidate for candidate in candidates if candidate]


def normalize_avatar_url(avatar_url):
    if not avatar_url:
        return None

    avatar_url = avatar_url.strip()

    if (
        is_real_avatar_url(avatar_url)
        and '_medium' not in avatar_url
        and avatar_url.lower().endswith('.jpg')
    ):
        return avatar_url[:-4] + '_medium.jpg'

    return avatar_url


def is_frame_or_decoration_url(url):
    if not url:
        return False

    url = url.strip().lower()

    frame_markers = [
        'profile_frame',
        'profileframe',
        'avatar_frame',
        'avatarframe',
        'animated_avatar',
        'miniprofile',
        'economy/image',
        'communityitems',
        'items/',
        'border',
        'frame',
    ]

    return any(marker in url for marker in frame_markers)


def extract_avatar_url(comment_node):
    avatar_container = comment_node.select_one('.commentthread_comment_avatar')

    if not avatar_container:
        return None

    # First check media inside the profile link.
    # That is where the real avatar lives, including animated avatars.
    profile_media_tags = avatar_container.select('a img, a source')

    animated_candidates = []
    static_candidates = []

    for media_tag in profile_media_tags:
        for url in get_candidate_urls(media_tag):
            normalized_url = normalize_avatar_url(url)

            if not normalized_url:
                continue

            if normalized_url.lower().endswith('.gif'):
                animated_candidates.append(normalized_url)
                continue

            if is_real_avatar_url(normalized_url) or '/community_assets/images/items/' in normalized_url:
                static_candidates.append(normalized_url)

    if animated_candidates:
        return animated_candidates[0]

    if static_candidates:
        return static_candidates[0]

    image_tags = avatar_container.select('img')

    # First try to find a real avatar URL.
    for image_tag in image_tags:
        for url in get_candidate_urls(image_tag):
            if is_real_avatar_url(url):
                return normalize_avatar_url(url)

    # Fallback: use the last image that does not look like a frame.
    for image_tag in reversed(image_tags):
        for url in get_candidate_urls(image_tag):
            if url and not is_frame_or_decoration_url(url):
                return normalize_avatar_url(url)

    return None


def parse_timestamp(comment_node):
    timestamp_node = comment_node.find(attrs={'data-timestamp': True})

    if timestamp_node:
        try:
            unix_timestamp = int(timestamp_node['data-timestamp'])
            return datetime.fromtimestamp(unix_timestamp, tz=timezone.utc).isoformat()
        except ValueError:
            pass

    return datetime.now(timezone.utc).isoformat()


def extract_comments_from_html(html_text):
    comments = []
    soup = bs4.BeautifulSoup(html_text, 'html.parser')

    for single_comment in soup.select('.commentthread_comment.responsive_body_text'):
        try:
            author_tag = single_comment.find('bdi')
            message_tag = single_comment.select_one('.commentthread_comment_text')

            if not author_tag or not message_tag:
                continue

            avatar_url = extract_avatar_url(single_comment)

            comments.append({
                'author': author_tag.get_text(strip=True),
                'avatar': avatar_url,
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
            params={
                'count': page_size,
                'start': start,
                'totalcount': start,
            },
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

    try:
        with file_path.open('r', encoding='utf-8') as file:
            data = json.load(file)
            return data.get('comments', [])
    except Exception as error:
        print(f'Could not read {file_path}: {error}')
        return []


def should_replace_avatar(old_avatar, new_avatar):
    if not new_avatar:
        return False

    if not old_avatar:
        return True

    old_is_real = is_real_avatar_url(old_avatar)
    new_is_real = is_real_avatar_url(new_avatar)

    if not old_is_real and new_is_real:
        return True

    if is_frame_or_decoration_url(old_avatar) and new_is_real:
        return True

    return False


def merge_comments(existing_comments, live_comments):
    merged = {}

    # Existing comments first, then live comments.
    # This lets live data replace older bad avatar values.
    for comment in existing_comments + live_comments:
        key = (
            comment.get('author', '').strip(),
            comment.get('comment', '').strip(),
            comment.get('timestamp', '').strip(),
        )

        new_avatar = comment.get('avatar')

        if key not in merged:
            merged[key] = {
                'author': comment.get('author'),
                'avatar': new_avatar,
                'timestamp': comment.get('timestamp'),
                'comment': comment.get('comment'),
            }
            continue

        old_avatar = merged[key].get('avatar')

        if should_replace_avatar(old_avatar, new_avatar):
            merged[key]['avatar'] = new_avatar

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
            print(f"Processing {guide['url']}")

            live_comments = fetch_live_comments(guide)
            existing_comments = load_existing_comments(guide['output'])
            merged_comments = merge_comments(existing_comments, live_comments)

            save_comments_to_json(merged_comments, guide['output'])

            print(
                f"Saved comments to docs/{guide['output']} "
                f"(visible live comments: {len(live_comments)}, "
                f"total stored comments: {len(merged_comments)})"
            )
        except Exception as error:
            print(f"Error processing {guide['url']}: {error}")


if __name__ == '__main__':
    main()
