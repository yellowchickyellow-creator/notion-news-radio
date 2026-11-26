"""Check the deployed episode metadata and MP3 hashes, allowing CDN propagation."""
import hashlib
import json
import time
import requests
from radio import BASE, EPISODES
from build_audio import OUT

expected = json.loads((OUT / 'episodes.json').read_text(encoding='utf-8'))
for attempt in range(6):
    try:
        suffix = '?v=' + str(time.time_ns())
        response = requests.get(BASE + 'episodes.json' + suffix, timeout=35)
        response.raise_for_status()
        assert response.json() == expected, '公開情報が一致しません'
        for episode, meta in expected.items():
            if meta is None:
                continue
            filename = EPISODES[episode][0] + '.mp3'
            response = requests.get(BASE + filename + suffix, timeout=60)
            response.raise_for_status()
            assert hashlib.sha256(response.content).digest() == hashlib.sha256((OUT / filename).read_bytes()).digest(), filename
        response = requests.get(BASE + suffix, timeout=35)
        response.raise_for_status()
        assert response.content == (OUT / 'index.html').read_bytes(), 'プレイヤーが一致しません'
        print('公開HTML・朝夜の情報・MP3の一致を確認しました')
        break
    except (requests.RequestException, AssertionError):
        if attempt == 5:
            raise
        time.sleep(15)
