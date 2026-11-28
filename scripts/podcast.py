"""Build two independent podcast feeds without changing the daily player."""
import asyncio
import hashlib
import tempfile
import json
import shutil
import struct
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import requests
from radio import BASE, EPISODES, duration, mix, episode_voice
from build_audio import OUT, save_mp3

LIMIT = 30
MANIFEST = 'podcast-history.json'
ITUNES = 'http://www.itunes.com/dtds/podcast-1.0.dtd'
ATOM = 'http://www.w3.org/2005/Atom'
ET.register_namespace('itunes', ITUNES)
ET.register_namespace('atom', ATOM)

def fetch(path, optional=False):
    response = requests.get(BASE + path, params={'v': str(time.time_ns())}, timeout=(15, 90))
    if optional and response.status_code == 404:
        return None
    response.raise_for_status()
    return response.content

def sha(data):
    return hashlib.sha256(data).hexdigest()

def episode_path(show, day, digest):
    day = date.fromisoformat(day).isoformat()
    if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('invalid podcast checksum')
    if show not in EPISODES:
        raise ValueError('unknown show')
    return f'podcast/{show}/{day}-{digest[:16]}.mp3'

def write_audio(path, data, entry):
    if len(data) != entry['length'] or sha(data) != entry['sha256']:
        raise ValueError(f'podcast checksum/length mismatch: {entry["date"]}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

def previous_history():
    raw = fetch(MANIFEST, optional=True)
    if raw is None:
        # Absence is acceptable only before the first podcast deployment.
        for show in EPISODES:
            if fetch(f'{show}.xml', optional=True) is not None:
                raise RuntimeError('Podcast history missing; refusing to erase published episodes')
        return {show: [] for show in EPISODES}
    obj = json.loads(raw)
    if obj.get('version') != 1 or set(obj['shows']) != set(EPISODES):
        raise ValueError('unsupported podcast history')
    return obj['shows']

def migrate(out):
    """Use the current published assets instead of regenerating today's voice."""
    out.mkdir(parents=True, exist_ok=True)
    episodes = json.loads(fetch('episodes.json'))
    if not episodes.get('morning') or not episodes.get('evening'):
        raise RuntimeError('Both current programs must be available for initial migration')
    for show, (stem, _) in EPISODES.items():
        meta = episodes[show]
        audio = fetch(stem + '.mp3')
        if len(audio) < 8192 or (meta.get('audio_sha256') and sha(audio) != meta['audio_sha256']):
            raise ValueError(f'published {show} audio is invalid')
        path = out / (stem + '.mp3')
        path.write_bytes(audio)
        if duration(path) <= 0:
            raise ValueError('invalid MP3 duration')
        (out / (stem + '.txt')).write_bytes(fetch(stem + '.txt'))
        status = 'status.json' if show == 'morning' else 'evening-status.json'
        (out / status).write_bytes(fetch(status))
    (out / 'episodes.json').write_text(json.dumps(episodes, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copyfile(Path(__file__).with_name('player.html'), out / 'index.html')
    (out / '.nojekyll').touch()

def create_entry(show, meta, audio):
    d = date.fromisoformat(meta['date_jst']).isoformat()
    digest = sha(audio)
    if meta.get('audio_sha256') and digest != meta['audio_sha256']:
        raise ValueError('daily audio checksum mismatch')
    if len(audio) < 8192:
        raise ValueError('daily audio too small')
    generated = datetime.fromisoformat(meta['generated_at_jst'].replace('Z', '+00:00'))
    if generated.tzinfo is None:
        from zoneinfo import ZoneInfo
        generated = generated.replace(tzinfo=ZoneInfo('Asia/Tokyo'))
    seconds = float(meta['duration_seconds'])
    if not 0 < seconds < 86400:
        raise ValueError('invalid duration')
    return {'date': d, 'sha256': digest, 'length': len(audio),
            'duration': round(seconds), 'pubdate': format_datetime(generated.astimezone(timezone.utc), usegmt=True),
            'path': episode_path(show, d, digest)}

def rss(show, entries):
    root = ET.Element('rss', {'version': '2.0'})
    channel = ET.SubElement(root, 'channel')
    title = '車内ラジオ｜' + EPISODES[show][1]
    description = ('毎日の重要ニュースと背景解説をお届けします。' if show == 'morning'
                   else '帰宅時に楽しむ生活と教養のラジオです。')
    def add(parent, name, value):
        ET.SubElement(parent, name).text = str(value)
    add(channel, 'title', title)
    add(channel, 'link', BASE)
    add(channel, 'description', description)
    add(channel, 'language', 'ja')
    add(channel, f'{{{ITUNES}}}author', '車内ラジオ')
    add(channel, f'{{{ITUNES}}}explicit', 'false')
    add(channel, f'{{{ITUNES}}}type', 'episodic')
    # No submission to the public Apple Podcasts directory is needed for URL following.
    ET.SubElement(channel, f'{{{ATOM}}}link', {'href': BASE + show + '.xml', 'rel': 'self', 'type': 'application/rss+xml'})
    ET.SubElement(channel, f'{{{ITUNES}}}category', {'text': 'News' if show == 'morning' else 'Education'})
    ET.SubElement(channel, f'{{{ITUNES}}}image', {'href': BASE + show + '-cover.png'})
    for entry in entries:
        item = ET.SubElement(channel, 'item')
        d = date.fromisoformat(entry['date'])
        test = entry.get('test', False)
        label = '【テスト】' if test else ''
        add(item, 'title', f'{label}{d.year}年{d.month}月{d.day}日｜{EPISODES[show][1]}')
        add(item, 'description', '翌日更新と男性音声の動作確認用。前回の原稿を再収録しています。' if test else description)
        guid = f'notion-news-radio:{show}:{entry["date"]}'
        ET.SubElement(item, 'guid', {'isPermaLink': 'false'}).text = guid + (':test' if test else '')
        add(item, 'pubDate', entry['pubdate'])
        add(item, f'{{{ITUNES}}}duration', entry['duration'])
        ET.SubElement(item, 'enclosure', {'url': BASE + entry['path'], 'length': str(entry['length']), 'type': 'audio/mpeg'})
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)

def cover(show):
    """Small original radio icon, 1400px RGB PNG, no external image dependencies."""
    size = 1400
    bg = (23, 37, 58) if show == 'morning' else (39, 30, 65)
    fg = (242, 202, 123) if show == 'morning' else (203, 193, 250)
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            # Rounded appearance through a circular outline and broadcast rings.
            r2 = (x - 700)**2 + (y - 700)**2
            on = (510**2 < r2 < 535**2 or
                  (570 <= x <= 830 and 410 <= y <= 810 and
                   (500 <= y <= 720 or (x-700)**2+(y-(500 if y<500 else 720))**2 < 130**2)) or
                  (460**2 < (x-700)**2+(y-620)**2 < 478**2 and y > 620 and 410 < x < 990) or
                  (675 <= x <= 725 and 810 <= y <= 1020) or (520 <= x <= 880 and 995 <= y <= 1030))
            raw.extend(fg if on else bg)
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')

def build(out, history=None, downloader=fetch, test_evening=False):
    episodes = json.loads((out / 'episodes.json').read_text(encoding='utf-8'))
    old = previous_history() if history is None else history
    result = {}
    for show, (stem, _) in EPISODES.items():
        known = {}
        for entry in old[show]:
            if entry['path'] != episode_path(show, entry['date'], entry['sha256']):
                raise ValueError('invalid history path')
            key = (entry['date'], bool(entry.get('test')))
            if key in known:
                raise ValueError('duplicate history date and type')
            known[key] = entry
        current = episodes.get(show)
        if current:
            audio = (out / (stem + '.mp3')).read_bytes()
            entry = create_entry(show, current, audio)
            # First published version for a date is immutable. Reruns cannot replace it.
            key = (entry['date'], False)
            if key not in known:
                write_audio(out / entry['path'], audio, entry)
                known[key] = entry
            elif known[key]['sha256'] == entry['sha256']:
                write_audio(out / entry['path'], audio, entry)
        if test_evening and show == 'evening':
            if not current:
                raise RuntimeError('No evening audio for test')
            day = (date.fromisoformat(current['date_jst']) + timedelta(days=1)).isoformat()
            key = (day, True)
            if key not in known:
                from zoneinfo import ZoneInfo
                now = datetime.now(ZoneInfo('Asia/Tokyo'))
                script = ('こんばんは。これは翌日分の自動再生を確かめるためのテスト放送です。'
                          '男性ナレーターで、前回の夜の原稿を再収録します。\n'
                          + (out / (stem + '.txt')).read_text(encoding='utf-8'))
                with tempfile.TemporaryDirectory() as directory:
                    tmp = Path(directory)
                    voice, final = tmp / 'voice.mp3', tmp / 'final.mp3'
                    asyncio.run(save_mp3(script, voice, voice=episode_voice('evening')))
                    seconds = mix(voice, final, 'evening', tmp)
                    audio = final.read_bytes()
                entry = create_entry(show, {'date_jst': day, 'generated_at_jst': now.isoformat(),
                                            'duration_seconds': seconds}, audio)
                entry['test'] = True
                entry['voice'] = episode_voice('evening')
                write_audio(out / entry['path'], audio, entry)
                known[key] = entry
                print(f'Evening test published for {day}: {seconds:.1f}s, {entry["voice"]}')
        entries = sorted(known.values(), key=lambda e: (e['date'], not e.get('test', False)), reverse=True)[:LIMIT]
        def restore(e):
            target = out / e['path']
            if not target.exists():
                write_audio(target, downloader(e['path']), e)
            else:
                data = target.read_bytes()
                if sha(data) != e['sha256'] or len(data) != e['length']:
                    raise ValueError('invalid local archive')
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(restore, entries))
        if not entries:
            raise RuntimeError(f'No episodes available for {show}')
        (out / (show + '.xml')).write_bytes(rss(show, entries))
        (out / (show + '-cover.png')).write_bytes(cover(show))
        result[show] = entries
    (out / MANIFEST).write_text(json.dumps({'version': 1, 'shows': result}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Podcast feeds built:', ', '.join(f'{s}={len(e)}' for s,e in result.items()))

def verify_public(out):
    history = json.loads((out / MANIFEST).read_text(encoding='utf-8'))
    assert json.loads(fetch(MANIFEST)) == history, 'public history differs'
    for show, entries in history['shows'].items():
        name = show + '.xml'
        expected = (out / name).read_bytes()
        actual = fetch(name)
        assert actual == expected, name
        items = ET.fromstring(actual).findall('./channel/item')
        assert len(items) == len(entries)
        assert len({i.findtext('guid') for i in items}) == len(items)
        for item, entry in zip(items, entries):
            enclosure = item.find('enclosure')
            assert enclosure.attrib == {'url': BASE + entry['path'], 'length': str(entry['length']), 'type': 'audio/mpeg'}
            # Check every archive remains reachable and the latest is byte-identical.
            r = requests.head(BASE + entry['path'], timeout=30, allow_redirects=True)
            r.raise_for_status()
            if r.headers.get('Content-Length'):
                assert int(r.headers['Content-Length']) == entry['length']
        data = fetch(entries[0]['path'])
        assert sha(data) == entries[0]['sha256']
        assert fetch(show + '-cover.png') == (out / (show + '-cover.png')).read_bytes()
    print('Public podcast feeds, archive URLs and latest audio hashes verified')

if __name__ == '__main__':
    if '--migrate' in sys.argv:
        migrate(OUT)
    else:
        build(OUT, test_evening='--test-evening' in sys.argv)
