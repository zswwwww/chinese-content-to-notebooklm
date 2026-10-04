import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from filelock import FileLock

from notebooklm_combo import cleanup as cleanup_audio, ingest
from notebooklm_combo._vendor.chubbyskills import bilibili


class CleanupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / 'cache'
        self.root.mkdir()
        self.now = time.time()

    def audio(self, key='a' * 16, age_days=8):
        folder = self.root / key
        folder.mkdir(exist_ok=True)
        path = folder / 'audio.mp3'
        path.write_bytes(b'test-audio')
        stamp = self.now - age_days * 86400
        os.utime(path, (stamp, stamp))
        return path

    def test_deletes_only_expired_named_audio(self):
        old = self.audio()
        recent = self.audio('b' * 16, 1)
        transcript = old.parent / 'source.md'
        transcript.write_text('retained text')
        other_audio = old.parent / 'personal.mp3'
        other_audio.write_bytes(b'retained')
        outside = self.base / 'audio.mp3'
        outside.write_bytes(b'retained')
        result = cleanup_audio.cleanup(self.root, apply=True, now=self.now)
        self.assertFalse(old.exists())
        self.assertTrue(all(p.exists() for p in (recent, transcript, other_audio, outside)))
        self.assertEqual(result['bytes_deleted'], len(b'test-audio'))

    def test_preview_never_deletes(self):
        path = self.audio()
        result = cleanup_audio.cleanup(self.root, now=self.now)
        self.assertTrue(path.exists())
        self.assertEqual(len(result['eligible']), 1)
        self.assertEqual(result['deleted'], [])

    def test_linked_directory_is_not_cleaned(self):
        outside = self.base / 'outside'
        outside.mkdir()
        audio = outside / 'audio.mp3'
        audio.write_bytes(b'private audio')
        stamp = self.now - 9 * 86400
        os.utime(audio, (stamp, stamp))
        link = self.root / ('c' * 16)
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('This OS account cannot create symbolic links')
        result = cleanup_audio.cleanup(self.root, apply=True, now=self.now)
        self.assertTrue(audio.exists())
        self.assertEqual(result['deleted'], [])

    def test_active_lock_skips_audio(self):
        path = self.audio()
        with FileLock(str(path.parent / '.audio.lock')):
            result = cleanup_audio.cleanup(self.root, apply=True, now=self.now)
        self.assertTrue(path.exists())
        self.assertEqual(result['skipped'][0]['reason'], 'in_use')

    def test_seven_day_boundary_is_kept(self):
        boundary = self.audio(age_days=7)
        result = cleanup_audio.cleanup(self.root, apply=True, now=self.now)
        self.assertTrue(boundary.exists())
        self.assertEqual(result["bytes_deleted"], 0)

    def test_invalid_retention_is_rejected(self):
        for value in (0, True):
            with self.assertRaises(ValueError):
                cleanup_audio.cleanup(self.root, retention_days=value, apply=True)

    def test_extraction_protects_audio_and_refreshes_usage(self):
        observations = []

        def download(cfg, source, folder, filename):
            path = Path(folder) / filename
            path.write_bytes(b'downloaded')

        def transcribe(path):
            audio = Path(path)
            old = self.now - 9 * 86400
            os.utime(audio, (old, old))
            observations.append(cleanup_audio.cleanup(self.root, apply=True, now=self.now))
            self.assertTrue(audio.exists())
            return 'A useful transcript. ' * 10

        output = self.base / 'outputs'
        output.mkdir()
        with patch.object(ingest, "CONFIG", {"cache_dir": str(self.root), "bilibili_proxy": ""}), patch.object(bilibili, "get_info", return_value=("test", "author")), patch.object(bilibili, "try_subtitles", return_value=None), patch.object(bilibili.ytdlp, "download_audio", side_effect=download), patch.object(bilibili, "transcribe_audio", side_effect=transcribe):
            result = ingest.extract('bilibili', 'https://example.invalid/BVtest', output)
        self.assertEqual(observations[0]['skipped'][0]['reason'], 'in_use')
        self.assertTrue(Path(result['source_file']).exists())
        audio = next(self.root.glob('*/audio.mp3'))
        self.assertGreater(audio.stat().st_mtime, self.now - 60)


if __name__ == '__main__':
    unittest.main(verbosity=2)
