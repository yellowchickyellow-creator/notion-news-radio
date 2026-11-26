import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile
import json
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_audio as source
import radio

class RadioTests(unittest.TestCase):
    def test_all_segments_pagination_and_deep_children(self):
        def block(text, child=False):
            return {'id': text, 'type': 'paragraph', 'paragraph': {'rich_text': [{'plain_text':text}, {'plain_text':'後半'}]}, 'has_children':child}
        def fetch(session, path, params):
            if path=='root/children':
                return {'results':[block('最終')] } if params.get('start_cursor') else {'results':[block('1',True)],'next_cursor':'next'}
            n=int(path.split('/')[0])
            return {'results':[block(str(n+1),n<5)]}
        with patch.object(source,'get_json',side_effect=fetch):
            parts,_=source.collect_blocks(None,'root')
        self.assertEqual(parts,['1後半','2後半','3後半','4後半','5後半','6後半','最終後半'])

    def test_depth_overflow_fails_instead_of_truncating(self):
        with self.assertRaises(ValueError):
            source.collect_blocks(None,'id',31)

    def test_evening_failure_keeps_morning_publishable(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            def save(script,path): path.write_bytes(b'a'*9000)
            def mix(voice,final,episode,temp): final.write_bytes(voice.read_bytes()); return 390
            with patch.object(source,'OUT',out), patch.object(source,'read_today_script',side_effect=['朝'*3000,ValueError('private')]), patch.object(source,'save_mp3',save), patch.object(radio.asyncio,'run'), patch.object(radio,'mix',mix), patch.object(radio,'restore',return_value=None), patch.object(radio.Path,'write_text',autospec=True) as write:
                radio.main()
                metadata=[json.loads(c.args[1]) for c in write.call_args_list if str(c.args[0]).endswith('episodes.json')][0]
                self.assertIsNone(metadata['evening'])
                self.assertEqual(metadata['morning']['characters'],3000)
                self.assertTrue((out/'today.mp3').exists())

    def test_missing_morning_aborts_deployment(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(source,'OUT',Path(directory)), patch.object(source,'read_today_script',side_effect=ValueError()), patch.object(radio,'restore',return_value=None), patch.object(radio.Path,'write_text'):
            with self.assertRaises(RuntimeError): radio.main()

if __name__=='__main__': unittest.main()
