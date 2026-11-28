import hashlib
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import podcast

class PodcastTests(unittest.TestCase):
    def set_daily(self, out, day, data):
        meta = {'date_jst': day, 'generated_at_jst': day+'T07:30:00+09:00',
                'duration_seconds': 450, 'audio_sha256': hashlib.sha256(data).hexdigest()}
        for stem, _ in podcast.EPISODES.values():
            (out / (stem+'.mp3')).write_bytes(data)
        (out/'episodes.json').write_text(json.dumps({s:meta for s in podcast.EPISODES}))

    def test_daily_archive_rerun_and_next_day(self):
        empty = {s: [] for s in podcast.EPISODES}
        with tempfile.TemporaryDirectory() as d, patch.object(podcast,'cover',return_value=b'png'):
            p=Path(d)
            self.set_daily(p,'2026-11-28',b'a'*9000)
            podcast.build(p,empty)
            history=json.loads((p/podcast.MANIFEST).read_text())['shows']
            files={e['path']:(p/e['path']).read_bytes() for entries in history.values() for e in entries}
            for path in files:
                (p/path).unlink()
            self.set_daily(p,'2026-11-28',b'b'*9000)
            podcast.build(p,history,files.__getitem__)
            self.assertEqual(history,json.loads((p/podcast.MANIFEST).read_text())['shows'])
            self.set_daily(p,'2026-11-29',b'c'*9000)
            podcast.build(p,history,files.__getitem__)
            for show in podcast.EPISODES:
                items=ET.parse(p/(show+'.xml')).findall('./channel/item')
                self.assertEqual(len(items),2)
                self.assertNotEqual(items[0].findtext('guid'),items[1].findtext('guid'))
                self.assertEqual(items[1].find('enclosure').get('url'),podcast.BASE+history[show][0]['path'])

    def test_test_episode_does_not_replace_real_guid(self):
        meta = {'date_jst':'2026-11-29','generated_at_jst':'2026-11-29T01:00:00+09:00','duration_seconds':400}
        normal = podcast.create_entry('evening',meta,b'a'*9000)
        test = podcast.create_entry('evening',meta,b'b'*9000)
        test['test'] = True
        items = ET.fromstring(podcast.rss('evening',[normal,test])).findall('./channel/item')
        self.assertNotEqual(items[0].findtext('guid'),items[1].findtext('guid'))
        self.assertIn('【テスト】',items[1].findtext('title'))
        self.assertNotEqual(items[0].find('enclosure').get('url'),items[1].find('enclosure').get('url'))

    def test_corrupt_history_aborts(self):
        with tempfile.TemporaryDirectory() as d, patch.object(podcast,'cover',return_value=b'png'):
            p=Path(d)
            self.set_daily(p,'2026-11-28',b'a'*9000)
            podcast.build(p,{s:[] for s in podcast.EPISODES})
            old=json.loads((p/podcast.MANIFEST).read_text())['shows']
            for entries in old.values():
                (p/entries[0]['path']).unlink()
            self.set_daily(p,'2026-11-29',b'b'*9000)
            with self.assertRaises(ValueError):
                podcast.build(p,old,lambda _: b'wrong')

if __name__ == '__main__':
    unittest.main()
