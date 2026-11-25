"""Local tests of overlay utilities. Synthetic fixture only, never a submitted benchmark."""
import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import run_benchmark as b
import update_report as u

class ToolsTests(unittest.TestCase):
    def test_report_preserves_manual_notes(self):
        text='header\n<!-- BEGIN AUTO:LOAD -->\nold\n<!-- END AUTO:LOAD -->\nmanual trace and notes\n'
        new=u.replace_block(text,'LOAD','new')
        self.assertEqual(new,'header\n<!-- BEGIN AUTO:LOAD -->\nnew\n<!-- END AUTO:LOAD -->\nmanual trace and notes\n')
        self.assertEqual(u.replace_block(new,'LOAD','new'),new)
    def test_no_marker_does_not_replace(self):
        with self.assertRaises(ValueError): u.replace_block('manual','LOAD','new')
    def test_sync_preserves_evidence_and_conflicts(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); src=p/'src'; dst=p/'sub/dst'; src.write_text('original'); b.sync_one(src,dst)
            b.sync_one(src,dst); self.assertEqual(dst.read_text(),'original')
            src.write_text('other')
            with self.assertRaises(RuntimeError): b.sync_one(src,dst)
            self.assertEqual(dst.read_text(),'original')
    def test_legacy_migration(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); root=p/'root'; dev=p/'dev'; root.mkdir(); dev.mkdir()
            (root/'tail_003.json').write_text('{"fixture":true}')
            with patch.object(b,'ROOT_REPORTS',root),patch.object(b,'REPORTS',dev): b.sync_reports()
            self.assertEqual((root/'load_v2_slow_0.03.json').read_bytes(),(dev/'load_v2_slow_0.03.json').read_bytes())
            self.assertTrue((root/'tail_003.json').exists())
    def test_reuse_existing_report(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); (p/'load.json').write_text('{"slo":{"passed":false}}')
            with patch.object(b,'REPORTS',p),patch.object(b.subprocess,'run') as run:
                self.assertEqual(b.command('no-script',[],'load.json'),1); run.assert_not_called()
if __name__=='__main__': unittest.main(verbosity=2)
