#!/usr/bin/env python3
"""
微信公众号文章 → Markdown 提取工具

用法：
    python fetch_article.py "https://mp.weixin.qq.com/s/xxxxx"
    python fetch_article.py "https://mp.weixin.qq.com/s/xxxxx" --output ./output
    python fetch_article.py "path/to/article.pdf"  # PDF fallback
"""

import sys
import os
import re
import argparse
import urllib.parse
from pathlib import Path


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


def _image_url(tag):
    return tag.get("data-src") or tag.get("src") or tag.get("data-original") or ""


def _inline_markdown(node, source_url):
    """Render inline text while keeping links and simple emphasis."""
    from bs4 import NavigableString, Tag

    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""
    if node.name == "br":
        return "\n"
    if node.name == "img":
        src = _image_url(node)
        if not src:
            return ""
        alt = _clean_text(node.get("alt", ""))
        return f"![{alt}]({urllib.parse.urljoin(source_url, src)})"
    text = "".join(_inline_markdown(child, source_url) for child in node.children)
    text = _clean_text(text)
    if not text:
        return ""
    if node.name == "a":
        href = node.get("href", "")
        if href:
            return f"[{text}]({urllib.parse.urljoin(source_url, href)})"
    if node.name in {"strong", "b"}:
        return f"**{text}**"
    if node.name in {"em", "i"}:
        return f"*{text}*"
    return text


def _block_markdown(node, source_url):
    from bs4 import NavigableString, Tag

    if isinstance(node, NavigableString):
        text = _clean_text(str(node))
        return [text] if text else []
    if not isinstance(node, Tag):
        return []
    if node.name in {"script", "style", "svg"}:
        return []
    if node.name == "img":
        src = _image_url(node)
        if not src:
            return []
        alt = _clean_text(node.get("alt", ""))
        return [f"![{alt}]({urllib.parse.urljoin(source_url, src)})"]
    if node.name in {"h1", "h2", "h3", "h4"}:
        level = min(int(node.name[1]), 4)
        text = _clean_text(node.get_text(" ", strip=True))
        return [f"{'#' * level} {text}"] if text else []

    block_children = [
        child for child in node.children
        if getattr(child, "name", None) in {"p", "section", "div", "blockquote", "ul", "ol", "li", "h1", "h2", "h3", "h4", "img"}
    ]
    if block_children and node.name in {"section", "div", "article"}:
        out = []
        for child in node.children:
            out.extend(_block_markdown(child, source_url))
        return out

    if node.name == "blockquote":
        text = _clean_text(_inline_markdown(node, source_url))
        return ["> " + text] if text else []
    if node.name == "li":
        text = _clean_text(_inline_markdown(node, source_url))
        return [f"- {text}"] if text else []

    text = _clean_text(_inline_markdown(node, source_url))
    return [text] if text else []


def html_to_markdown(content_tag, source_url):
    blocks = []
    for child in content_tag.children:
        blocks.extend(_block_markdown(child, source_url))

    cleaned = []
    seen = set()
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # WeChat pages often repeat hidden share images; dedupe exact blocks.
        if block.startswith("![") and block in seen:
            continue
        seen.add(block)
        cleaned.append(block)
    return "\n\n".join(cleaned)


def fetch_from_url(url: str) -> tuple:
    """Fetch article from WeChat URL. Returns (title, author, content)."""
    print(f"  🌐 Fetching: {url[:60]}...", file=sys.stderr)

    import httpx
    try:
        response = httpx.get(url, follow_redirects=True, timeout=30,
                             headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        html = response.text
    except httpx.HTTPError:
        print("  ❌ Fetch failed", file=sys.stderr)
        return None, None, None

    # Check if blocked
    if '环境异常' in html or '请在微信客户端' in html:
        print("  ❌ Blocked by WeChat", file=sys.stderr)
        return None, None, None

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
    except ImportError:
        print("  ❌ Need beautifulsoup4: pip install beautifulsoup4", file=sys.stderr)
        return None, None, None

    # Extract title
    title_tag = soup.find('h1', class_='rich_media_title')
    title = title_tag.get_text().strip() if title_tag else ""

    # Extract author/account
    author_tag = soup.find('span', class_='rich_media_meta_nickname')
    author = author_tag.get_text().strip() if author_tag else ""

    # Extract content
    content_tag = soup.find('div', class_='rich_media_content')
    if not content_tag:
        print("  ❌ No content found", file=sys.stderr)
        return None, None, None

    content = html_to_markdown(content_tag, url)

    if len(content) < 100:
        print(f"  ❌ Content too short ({len(content)} chars)", file=sys.stderr)
        return None, None, None

    print(f"  ✅ Fetched: {title[:50]}... ({len(content)} chars)", file=sys.stderr)
    return title, author, content


def extract_from_pdf(pdf_path: str) -> tuple:
    """Use the optional pypdf dependency to read a PDF text layer."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError('PDF support requires: pip install "chinese-content-to-notebooklm[pdf]"') from exc
    reader = PdfReader(pdf_path)
    content = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if len(content) < 100:
        return None, None, None
    return Path(pdf_path).stem, "", content


def generate_markdown(title: str, author: str, content: str, source: str) -> str:
    from .common.markdown import note_markdown
    return note_markdown(title or "公众号文章", content, {
        "type": "note", "platform": "wechat", "tags": ["公众号"],
        "author": author or "", "source": source,
    })


def sanitize_filename(name: str) -> str:
    """Clean filename."""
    s = re.sub(r'[<>:"/\\|?*]', '', name)
    s = re.sub(r'\s+', '-', s)
    return s[:50]


def main():
    parser = argparse.ArgumentParser(description='微信公众号文章 → Markdown')
    parser.add_argument('input', help='公众号链接或 PDF 文件路径')
    parser.add_argument('--output', '-o', default='.', help='输出目录')
    args = parser.parse_args()

    source = args.input

    # Determine input type
    if source.startswith('http'):
        title, author, content = fetch_from_url(source)
    elif os.path.exists(source):
        title, author, content = extract_from_pdf(source)
    else:
        print(f"❌ Invalid input: {source}", file=sys.stderr)
        sys.exit(1)

    if not content:
        print("❌ Failed to extract content", file=sys.stderr)
        sys.exit(1)

    # Generate markdown
    markdown = generate_markdown(title, author, content, source)

    # Save
    safe_title = sanitize_filename(title)
    output_filename = f"{safe_title}.md"
    output_path = os.path.join(args.output, output_filename)

    os.makedirs(args.output, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown)

    print(f"\n✅ Saved: {output_path}", file=sys.stderr)
    print(output_path)


if __name__ == '__main__':
    main()
