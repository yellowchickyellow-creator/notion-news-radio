"""Independent morning/evening builds; preserve the last valid episode on failure."""
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time
import wave
from datetime import datetime

import requests
import build_audio as source

BASE = 'https://yellowchickyellow-creator.github.io/notion-news-radio/'
EPISODES = {'morning': ('today', '朝のニュース'), 'evening': ('evening', '夜のひとやすみ')}


def command(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=180).stdout


def duration(path):
    return float(command(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                          '-of', 'default=noprint_wrappers=1:nokey=1', str(path)]))


def compose_bgm(path, evening=False):
    # Original procedural arrangement, no recordings, samples or quoted melodies.
    # 16 bars; slow sustained tones at night, gently plucked arpeggios in the morning.
    rate = 16000
    beat = 60 / (64 if evening else 96)
    chords = [(60, 64, 67, 71), (57, 60, 64, 67), (53, 57, 60, 64), (55, 59, 62, 69)]
    length = beat * 64
    with wave.open(str(path), 'wb') as wav:
        wav.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        for second in range(math.ceil(length)):
            samples = bytearray()
            for i in range(rate):
                t = second + i / rate
                if t >= length:
                    break
                chord = chords[int(t / (beat * 4)) % 4]
                phase = t % beat
                notes = chord if evening else [chord[int(t / beat) % 4]]
                envelope = (math.sin(math.pi * (t % (beat * 4)) / (beat * 4)) ** 2
                            if evening else (1 - math.exp(-phase * 60)) * math.exp(-phase * 5))
                tone = sum(math.sin(2 * math.pi * 440 * 2 ** ((n - 69) / 12) * t) for n in notes) / len(notes)
                fade = min(1, t / 2, (length - t) / 2)
                samples.extend(struct.pack('<h', int(24000 * tone * envelope * fade)))
            wav.writeframes(samples)


def mix(voice, output, episode, temp):
    seconds = duration(voice)
    if seconds <= 0:
        raise ValueError('音声の長さが不正です')
    if os.environ.get('BGM_ENABLED', 'true').lower() == 'false':
        shutil.copyfile(voice, output)
    else:
        music = temp / 'bgm.wav'
        compose_bgm(music, episode == 'evening')
        filters = (f'[0:a]loudnorm=I=-16:TP=-2:LRA=7[v];'
                   f'[1:a]volume=0.035,afade=t=in:d=2,afade=t=out:st={max(0, seconds-3)}:d=3[b];'
                   '[v][b]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=0[out]')
        command(['ffmpeg', '-v', 'error', '-y', '-i', str(voice), '-stream_loop', '-1', '-i', str(music),
                 '-filter_complex', filters, '-map', '[out]', '-t', str(seconds), '-ar', '24000',
                 '-c:a', 'libmp3lame', '-b:a', '96k', str(output)])
    actual = duration(output)
    if abs(actual - seconds) > 1 or output.stat().st_size < 8192:
        raise ValueError('合成した音声の長さ・サイズの検証に失敗しました')
    return actual


def restore(episode):
    """Read only fixed public assets, never credentials or arbitrary paths."""
    stem = EPISODES[episode][0]
    status_name = 'status.json' if episode == 'morning' else 'evening-status.json'
    try:
        response = requests.get(BASE + status_name, timeout=35)
        response.raise_for_status()
        meta = response.json()
        datetime.fromisoformat(meta['date_jst'])
        assets = {}
        for suffix in ('mp3', 'txt'):
            response = requests.get(BASE + stem + '.' + suffix, timeout=60)
            response.raise_for_status()
            assets[suffix] = response.content
        if len(assets['mp3']) < 8192:
            raise ValueError('previous audio too small')
        expected = meta.get('audio_sha256')
        if expected and hashlib.sha256(assets['mp3']).hexdigest() != expected:
            raise ValueError('previous audio checksum mismatch')
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / 'previous.mp3'
            candidate.write_bytes(assets['mp3'])
            duration(candidate)
        for suffix, data in assets.items():
            (source.OUT / f'{stem}.{suffix}').write_bytes(data)
        meta['retained'] = True
        (source.OUT / status_name).write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
        return meta
    except (requests.RequestException, ValueError, KeyError, subprocess.SubprocessError):
        return None


def main():
    source.OUT.mkdir(exist_ok=True)
    pages = {'morning': os.environ.get('NOTION_PAGE_ID', '').strip() or '406c2f0d-3b78-8160-a63f-e2057a7fe097',
             'evening': os.environ.get('NOTION_EVENING_PAGE_ID', '').strip() or '424c2f0d-3b78-81d7-82ab-ee281bf1ffb1'}
    episodes, failures = {}, []
    for episode, (stem, title) in EPISODES.items():
        stage = 'Notion原稿取得'
        try:
            script_date = datetime.now(source.TZ).date()
            for attempt in range(3):
                try:
                    script = source.read_today_script(pages[episode])
                    break
                except RuntimeError as error:
                    if str(error).startswith('Notion本文が今日更新されていません（本文最終更新: '):
                        print(f'{title}: {error}', flush=True)
                    if attempt == 2:
                        raise
                    time.sleep(90)
            print(f'{title}: Notion原稿 {len(script)}文字を取得', flush=True)
            with tempfile.TemporaryDirectory() as directory:
                temp = Path(directory)
                voice, final = temp / 'voice.mp3', temp / 'final.mp3'
                stage = '読み上げ音声生成'
                asyncio.run(source.save_mp3(script, voice))
                stage = 'BGM合成・尺検証'
                seconds = mix(voice, final, episode, temp)
                now = datetime.now(source.TZ)
                if now.date() != script_date:
                    raise RuntimeError('生成中に日付が変わったため、翌日分として公開しません')
                meta = {'date_jst': script_date.isoformat(), 'generated_at_jst': now.isoformat(),
                        'characters': len(script), 'duration_seconds': round(seconds, 2),
                        'voice': os.environ.get('TTS_VOICE', 'ja-JP-NanamiNeural'),
                        'bgm': os.environ.get('BGM_ENABLED', 'true').lower() != 'false',
                        'audio_sha256': hashlib.sha256(final.read_bytes()).hexdigest(), 'retained': False}
                shutil.copyfile(final, source.OUT / f'{stem}.mp3')
            (source.OUT / f'{stem}.txt').write_text(script, encoding='utf-8')
            status_name = 'status.json' if episode == 'morning' else 'evening-status.json'
            (source.OUT / status_name).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
            episodes[episode] = meta
            print(f'{title}: {len(script)}文字 / {seconds:.1f}秒')
        except Exception as error:
            # Do not log response bodies, text, tokens or request headers.
            detail = ''
            if stage == 'Notion原稿取得' and isinstance(error, ValueError):
                for message in (
                    'Notionのキー・ページID・対象ページへのインテグレーション接続を確認してください',
                    'Notionの原稿が100文字未満です。ページID、本文、アクセス権を確認してください',
                    'Notion本文の階層が深すぎます。全文を保証できないため停止します',
                ):
                    if str(error) == message:
                        detail = f'。{message}'
                        break
            print(f'::warning::{title}の更新失敗: {stage} ({type(error).__name__}){detail}', flush=True)
            failures.append(episode)
            episodes[episode] = restore(episode)
    Path('build-report.json').write_text(json.dumps({'failures': failures}), encoding='utf-8')
    if not episodes.get('morning'):
        raise RuntimeError('朝用を維持できないため公開を中止します。既存サイトは変更されません。')
    (source.OUT / 'episodes.json').write_text(json.dumps(episodes, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copyfile(Path(__file__).with_name('player.html'), source.OUT / 'index.html')
    (source.OUT / '.nojekyll').touch()


if __name__ == '__main__':
    main()
