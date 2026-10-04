from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from notebooklm_combo import ingest
from notebooklm_combo.config import load_config


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.source = self.root / 'notes.md'
        self.source.write_text('# Notes\n' + 'A source sentence. ' * 20, encoding='utf-8')
        self.output = self.root / 'outputs'
        self.config = self.root / 'settings.json'
        self.config.write_text(json.dumps({'cache_dir': str(self.root / 'cache')}), encoding='utf-8')
        self.args = [str(self.source), '--output', str(self.output), '--config', str(self.config)]
        self.calls = []
        self.fail_wait = False

    def remote(self, *args, **kwargs):
        self.calls.append(args)
        if args[:2] == ('notebook', 'list'):
            return []
        if args[:2] == ('notebook', 'create'):
            return {'notebook_id': 'test-notebook', 'url': 'https://example.invalid/notebook'}
        if args[:2] == ('source', 'add'):
            return {'source_id': 'test-source'}
        if args[:2] == ('notebook', 'query'):
            self.assertEqual(args[args.index('--source-ids') + 1], 'test-source')
            return {'answer': 'A grounded summary [1]', 'references': [{'source_id': 'test-source'}]}
        raise AssertionError(args)

    def run_main(self, args=None):
        with redirect_stdout(io.StringIO()), patch.object(ingest, 'nlm', side_effect=self.remote), patch.object(
            ingest, 'wait_source', side_effect=RuntimeError('index pending') if self.fail_wait else None
        ):
            return ingest.main(args or self.args)

    def state(self):
        return next(self.output.glob('*/result.json'))

    def test_success_and_repeat_reuse_remote_ids(self):
        self.run_main()
        self.run_main()
        self.assertEqual(sum(c[:2] == ('notebook', 'create') for c in self.calls), 1)
        self.assertEqual(sum(c[:2] == ('source', 'add') for c in self.calls), 1)
        self.assertEqual(sum(c[:2] == ('notebook', 'query') for c in self.calls), 1)
        state = json.loads(self.state().read_text(encoding='utf-8'))
        self.assertEqual(state['stage'], 'complete')
        self.assertIn('A grounded summary [1]', Path(state['summary_file']).read_text(encoding='utf-8'))

    def test_processing_failure_keeps_ids_and_resume_does_not_upload_again(self):
        self.fail_wait = True
        with self.assertRaisesRegex(RuntimeError, 'index pending'):
            self.run_main()
        state = json.loads(self.state().read_text(encoding='utf-8'))
        self.assertEqual((state['stage'], state['source_id']), ('uploaded', 'test-source'))
        self.fail_wait = False
        self.run_main()
        self.assertEqual(sum(c[:2] == ('source', 'add') for c in self.calls), 1)

    def test_unknown_create_stops_without_another_create(self):
        self.run_main(self.args + ['--extract-only'])
        state = json.loads(self.state().read_text(encoding='utf-8'))
        state['stage'] = 'creating'
        self.state().write_text(json.dumps(state), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, '结果不确定'):
            self.run_main()
        self.assertFalse(any(c[:2] == ('notebook', 'create') for c in self.calls))

    def test_unknown_upload_stops_without_another_upload(self):
        self.run_main(self.args + ['--extract-only'])
        state = json.loads(self.state().read_text(encoding='utf-8'))
        state.update(stage='uploading', notebook_id='test-notebook')
        self.state().write_text(json.dumps(state), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, '上传结果不确定'):
            self.run_main()
        self.assertFalse(any(c[:2] == ('source', 'add') for c in self.calls))

    def test_extract_only_never_contacts_notebooklm(self):
        self.run_main(self.args + ['--extract-only'])
        self.assertEqual(self.calls, [])
        self.assertEqual(json.loads(self.state().read_text(encoding='utf-8'))['stage'], 'extracted')

    def test_new_question_queries_same_source(self):
        self.run_main()
        self.run_main(self.args + ['--question', 'What supports the conclusion?'])
        self.assertEqual(sum(c[:2] == ('source', 'add') for c in self.calls), 1)
        self.assertEqual(sum(c[:2] == ('notebook', 'query') for c in self.calls), 2)

    def test_local_content_change_uses_new_state_directory(self):
        self.run_main(self.args + ['--extract-only'])
        self.source.write_text('Changed content', encoding='utf-8')
        self.run_main(self.args + ['--extract-only'])
        self.assertEqual(len(list(self.output.glob('*/result.json'))), 2)

    def test_empty_file_is_rejected_before_remote_calls(self):
        self.source.write_text('', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '本地文件为空'):
            self.run_main()
        self.assertEqual(self.calls, [])

    def test_missing_local_copy_does_not_reset_unknown_remote_state(self):
        self.run_main(self.args + ['--extract-only'])
        state = json.loads(self.state().read_text(encoding='utf-8'))
        Path(state['source_file']).unlink()
        state['stage'] = 'creating'
        self.state().write_text(json.dumps(state), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, '结果不确定'):
            self.run_main()
        self.assertFalse(any(c[:2] == ('notebook', 'create') for c in self.calls))


class SourceAndConfigTests(unittest.TestCase):
    def test_bv_and_tracking_url_normalize(self):
        expected = ('bilibili', 'https://www.bilibili.com/video/BV1kEVV6yEYf/')
        self.assertEqual(ingest.normalize_source('BV1kEVV6yEYf'), expected)
        self.assertEqual(ingest.normalize_source(expected[1] + '?spm_id_from=tracking'), expected)

    def test_watchlater_keeps_part(self):
        self.assertEqual(ingest.normalize_source('https://www.bilibili.com/list/watchlater/?bvid=BVtest&p=2')[1],
                         'https://www.bilibili.com/video/BVtest/?p=2')

    def test_invalid_part_and_unsupported_url_rejected(self):
        for source in ('https://www.bilibili.com/video/BVtest/?p=0', 'https://example.invalid/a'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                ingest.normalize_source(source)

    def test_proxy_override_and_restoration(self):
        original = ingest.CONFIG
        self.addCleanup(setattr, ingest, 'CONFIG', original)
        ingest.CONFIG = {'notebooklm_proxy': ''}
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://example.invalid:8080'}):
            with ingest.notebooklm_proxy():
                self.assertEqual(os.environ['HTTP_PROXY'], '')
                self.assertEqual(os.environ['ALL_PROXY'], '')
            self.assertEqual(os.environ['HTTP_PROXY'], 'http://example.invalid:8080')

    def test_bilibili_proxy_does_not_accumulate(self):
        from notebooklm_combo._vendor.chubbyskills import bilibili
        before = bilibili.CFG
        for _ in range(2):
            with ingest.bilibili_adapter({'bilibili_proxy': ''}) as module:
                self.assertEqual(module.CFG.extra_ydl_args, before.extra_ydl_args + ('--proxy', ''))
        self.assertEqual(bilibili.CFG, before)

    def test_relative_config_and_unknown_setting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps({'cache_dir': 'cache'}), encoding='utf-8')
            self.assertEqual(load_config(path)['cache_dir'], str(Path(folder) / 'cache'))
            path.write_text(json.dumps({'cookie': 'not a supported setting'}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '未知配置项'):
                load_config(path)

    def test_invalid_retention(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            for value in (0, -1, True, '7'):
                path.write_text(json.dumps({'retention_days': value}), encoding='utf-8')
                with self.subTest(value=value), self.assertRaises(ValueError):
                    load_config(path)
