"""Notion内の同一ページからニュースを読み取り、今日のラジオ用MP3を作る。"""
import asyncio
import html
import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import edge_tts
import requests

TZ = ZoneInfo("Asia/Tokyo")
API_VERSION = "2026-03-11"
BLOCKS_URL = "https://api.notion.com/v1/blocks"
OUT = Path(__file__).resolve().parents[1] / "site"
TEXT_TYPES = {
    "paragraph", "heading_1", "heading_2", "heading_3", "quote",
    "bulleted_list_item", "numbered_list_item", "callout", "toggle",
}


def get_json(session: requests.Session, path: str, params=None) -> dict:
    for attempt in range(4):
        resp = session.get(f"{BLOCKS_URL}/{path}", params=params, timeout=35)
        if resp.status_code in {429, 500, 502, 503, 504} and attempt < 3:
            time.sleep(min(30, max(1, int(resp.headers.get("Retry-After", 2 ** attempt)))))
            continue
        if resp.status_code in {401, 403, 404}:
            raise ValueError("Notionのキー・ページID・対象ページへのインテグレーション接続を確認してください")
        resp.raise_for_status()
        return resp.json()


def extract_text(block: dict) -> str:
    kind = block.get("type", "")
    data = block.get(kind, {})
    if kind in TEXT_TYPES or kind in {"code", "to_do"}:
        rich_text = data.get("rich_text", [])
        text = "".join(piece.get("plain_text", "") for piece in rich_text).strip()
        if kind == "to_do" and text:
            text = ("完了: " if data.get("checked") else "") + text
        return text
    if kind == "table_row":
        cells = data.get("cells", [])
        return "。".join("".join(p.get("plain_text", "") for p in cell) for cell in cells)
    return ""


def collect_blocks(session: requests.Session, parent_id: str, depth: int = 0):
    if depth > 30:
        raise ValueError("Notion本文の階層が深すぎます。全文を保証できないため停止します")
    parts, edited = [], []
    cursor = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        payload = get_json(session, f"{parent_id}/children", params)
        for block in payload.get("results", []):
            # 子ページやデータベースは別の資料なので収録しない
            if block.get("type") in {"child_page", "child_database", "link_to_page"}:
                continue
            fragment = extract_text(block)
            if fragment:
                parts.append(fragment)
                timestamp = block.get("last_edited_time")
                if timestamp:
                    edited.append(datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(TZ))
            if block.get("has_children"):
                nested, nested_edited = collect_blocks(session, block["id"], depth + 1)
                parts.extend(nested)
                edited.extend(nested_edited)
        cursor = payload.get("next_cursor")
        if not cursor:
            break
    return parts, edited


def read_today_script(page_id=None):
    token = os.environ["NOTION_API_KEY"].strip()
    page_id = page_id or os.environ["NOTION_PAGE_ID"].strip()
    with requests.Session() as session:
        session.headers.update({
            "Authorization": f"Bearer {token}",
            "Notion-Version": API_VERSION,
            "Content-Type": "application/json",
        })
        parts, edited = collect_blocks(session, page_id)
    script = "。\n".join(parts).strip()
    if len(script) < 100:
        raise ValueError("Notionの原稿が100文字未満です。ページID、本文、アクセス権を確認してください")
    if not edited or max(edited).date() != datetime.now(TZ).date():
        recent = max(edited).isoformat() if edited else "不明"
        raise RuntimeError(f"Notion本文が今日更新されていません（本文最終更新: {recent}）")
    return script


async def save_mp3(script: str, path: Path):
    voice = os.environ.get("TTS_VOICE", "ja-JP-NanamiNeural")
    rate = os.environ.get("TTS_RATE", "+0%")
    # edge-tts側が長文を分割して処理する。WindowsやEdge本体は不要。
    await asyncio.wait_for(edge_tts.Communicate(script, voice=voice, rate=rate).save(str(path)), timeout=600)
    if path.stat().st_size < 8192:
        raise RuntimeError("音声ファイルが小さすぎます。音声生成が失敗した可能性があります")


def write_page(script: str, date_label: str, iso_date: str, generated_at: str):
    OUT.mkdir(exist_ok=True)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    (OUT / "today.txt").write_text(script, encoding="utf-8")
    (OUT / "status.json").write_text(json.dumps({
        "date_jst": iso_date, "generated_at_jst": generated_at,
        "characters": len(script), "voice": os.environ.get("TTS_VOICE", "ja-JP-NanamiNeural"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    label = html.escape(date_label)
    (OUT / "index.html").write_text(f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#17253a"><title>今日のニュースラジオ</title>
<style>body{{font-family:system-ui,-apple-system,sans-serif;background:#f5f7fb;color:#1c2633;margin:0;padding:30px 14px}}main{{max-width:560px;margin:auto;background:white;padding:25px;border-radius:20px;box-shadow:0 8px 24px #17253a10}}h1{{font-size:1.55rem}}p{{line-height:1.7}}audio{{width:100%;margin:16px 0}}a{{color:#1656a2}}.small{{color:#69788c;font-size:0.85rem}}.warn{{background:#fff3d9;border-radius:10px;padding:12px}}</style></head>
<body><main><h1>🎧 今日のニュースラジオ</h1><p>生成日：<b>{label}</b></p>
<p class="warn" id="stale" hidden>この音声は今日のニュースではありません。更新状況を確認してください。</p>
<audio controls preload="metadata" src="today.mp3?v={iso_date}"></audio>
<p><a href="today.mp3?v={iso_date}">MP3を開く・保存する</a>　/　<a href="today.txt">原稿を読む</a></p>
<p class="small">日本時間 {html.escape(generated_at)} 生成。音声は公開URLで配信されます。</p></main>
<script>const today = new Intl.DateTimeFormat('en-CA',{{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}}).format(new Date());
if(today!=='{iso_date}')document.getElementById('stale').hidden=false;</script></body></html>''', encoding="utf-8")


def main():
    script = None
    for attempt in range(1, 4):
        try:
            script = read_today_script()
            break
        except RuntimeError as err:
            if attempt == 3:
                raise
            print(f"当日のNotion更新待ち ({attempt}/3): {err}", flush=True)
            time.sleep(90)
    assert script is not None
    now = datetime.now(TZ)
    iso = now.date().isoformat()
    label = f"{now.year}年{now.month}月{now.day}日"
    generated = now.strftime("%Y-%m-%d %H:%M")
    OUT.mkdir(exist_ok=True)
    asyncio.run(save_mp3(script, OUT / "today.mp3"))
    write_page(script, label, iso, generated)
    print(f"当日ニュース音声の生成が完了しました（原稿 {len(script)} 文字）")


if __name__ == "__main__":
    main()
