from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from notebooklm_combo import ingest
from notebooklm_combo._vendor.chubbyskills import bilibili, wechat


class ExtractionTests(unittest.TestCase):
    def test_wechat_html_preserves_title_links_and_body(self):
        text = 'This article explains an idea with supporting examples. ' * 6
        html = '<h1 class="rich_media_title">Title: subtitle</h1><span class="rich_media_meta_nickname">Author</span>'
        html += '<div class="rich_media_content"><p>' + text + '<a href="/reference">Reference</a></p></div>'
        with patch('httpx.get') as get:
            get.return_value.text = html
            title, author, body = wechat.fetch_from_url('https://mp.weixin.qq.com/s/test')
        self.assertEqual((title, author), ('Title: subtitle', 'Author'))
        self.assertIn('[Reference](https://mp.weixin.qq.com/reference)', body)
        self.assertIn('supporting examples', body)
        self.assertIn('"Title: subtitle"', wechat.generate_markdown(title, author, body, 'https://example.invalid'))

    def test_blocked_wechat_returns_no_content(self):
        with patch('httpx.get') as get:
            get.return_value.text = '<html>环境异常</html>'
            self.assertEqual(wechat.fetch_from_url('https://mp.weixin.qq.com/s/test'), (None, None, None))

    def test_pdf_text_layer_with_optional_dependency(self):
        with patch('pypdf.PdfReader') as reader:
            reader.return_value.pages[0].extract_text.return_value = 'PDF source text ' * 20
            reader.return_value.pages.__iter__.return_value = [reader.return_value.pages[0]]
            title, _, text = wechat.extract_from_pdf('my-file.pdf')
        self.assertEqual(title, 'my-file')
        self.assertIn('PDF source text', text)

    def test_subtitle_only_never_downloads_audio(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(bilibili, 'get_info', return_value=('title', 'author')), patch.object(
            bilibili, 'try_subtitles', return_value=None
        ), patch.object(bilibili.ytdlp, 'download_audio') as download:
            with self.assertRaisesRegex(ValueError, '未取得字幕'):
                ingest.extract('bilibili', 'https://www.bilibili.com/video/BVtest/', Path(folder), True)
            download.assert_not_called()

    def test_valid_subtitles_skip_audio(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(bilibili, 'get_info', return_value=('title', 'author')), patch.object(
            bilibili, 'try_subtitles', return_value=('Subtitle text. ' * 20, 'en')
        ), patch.object(bilibili.ytdlp, 'download_audio') as download:
            result = ingest.extract('bilibili', 'https://www.bilibili.com/video/BVtest/', Path(folder))
            self.assertEqual(result['method'], '字幕')
            self.assertIn('Subtitle text', Path(result['source_file']).read_text(encoding='utf-8'))
            download.assert_not_called()
