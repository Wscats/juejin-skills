"""Download Juejin articles and convert them to Markdown files."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from juejin_skill.api import JuejinAPI
from juejin_skill.config import (
    ARTICLE_DETAIL_URL,
    ARTICLE_QUERY_LIST_URL,
    DEFAULT_PAGE_SIZE,
    JUEJIN_WEB_URL,
    DEFAULT_HEADERS,
)
from juejin_skill.utils import (
    extract_article_id,
    extract_user_id,
    sanitize_filename,
    timestamp_to_str,
    ensure_dir,
)


class ArticleDownloader:
    """Download articles from Juejin and save them as Markdown files.

    Supports single-article download by URL/ID and batch download by user ID.
    Uses the Juejin API first, falling back to SSR HTML scraping when the API
    returns an error (e.g. parameter changes).
    """

    def __init__(self, cookie: str = "") -> None:
        self._api = JuejinAPI(cookie=cookie)

    # ------------------------------------------------------------------ #
    #  Single article
    # ------------------------------------------------------------------ #

    def download_article(
        self,
        url_or_id: str,
        output_dir: str = "./output",
        download_images: bool = False,
    ) -> dict[str, Any]:
        """Download one article and save it as a ``.md`` file.

        Parameters
        ----------
        url_or_id : str
            A Juejin post URL or a raw article ID.
        output_dir : str
            Directory to write the file.
        download_images : bool
            If ``True``, download embedded images to a local ``images/`` folder
            and rewrite image links.

        Returns
        -------
        dict
            ``{"success": True, "filepath": "...", "title": "..."}`` on success.
        """
        article_id = extract_article_id(url_or_id)
        if not article_id:
            return {"success": False, "message": f"Invalid article URL or ID: {url_or_id}"}

        # Try API first, then fallback to web scraping
        detail = self._fetch_article_detail(article_id)

        if detail:
            return self._save_from_api_detail(detail, article_id, output_dir, download_images)

        # Fallback: scrape from the SSR HTML page
        print(f"[Downloader] API failed, falling back to web scraping for {article_id}...")
        return self._save_from_web_scraping(article_id, output_dir, download_images)

    # ------------------------------------------------------------------ #
    #  Save from API detail data
    # ------------------------------------------------------------------ #

    def _save_from_api_detail(
        self,
        detail: dict[str, Any],
        article_id: str,
        output_dir: str,
        download_images: bool,
    ) -> dict[str, Any]:
        """Save an article from API detail response."""
        article_info = detail.get("article_info", {})
        author_info = detail.get("author_user_info", {})

        title = article_info.get("title", "Untitled")
        mark_content = article_info.get("mark_content", "")

        # If the article was written with the rich-text editor, mark_content
        # may be empty; fall back to converting HTML content.
        if not mark_content:
            html_content = article_info.get("content", "")
            if html_content:
                from markdownify import markdownify as md_convert
                mark_content = md_convert(html_content, heading_style="ATX", bullets="-")
            else:
                return {"success": False, "message": "Article has no downloadable content."}

        # Build metadata header
        tags = [t.get("tag_name", "") for t in detail.get("tags", [])]
        author_name = author_info.get("user_name", "Unknown")
        ctime = article_info.get("ctime", "0")

        return self._write_markdown_file(
            title=title,
            mark_content=mark_content,
            article_id=article_id,
            author=author_name,
            ctime=ctime,
            tags=tags,
            output_dir=output_dir,
            download_images=download_images,
        )

    # ------------------------------------------------------------------ #
    #  Fallback: scrape from SSR HTML
    # ------------------------------------------------------------------ #

    def _save_from_web_scraping(
        self,
        article_id: str,
        output_dir: str,
        download_images: bool,
    ) -> dict[str, Any]:
        """Scrape article content using Playwright to bypass WAF JS Challenge."""
        url = f"{JUEJIN_WEB_URL}/post/{article_id}"
        try:
            html = self._fetch_page_with_playwright(url)
        except Exception as exc:
            return {"success": False, "message": f"Failed to fetch web page: {exc}"}
        if not html:
            return {"success": False, "message": "Playwright returned empty page."}

        # Extract title and author with BeautifulSoup
        title = "Untitled"
        author = "Unknown"
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            # Title: look for h1.article-title first
            title_el = soup.find("h1", class_="article-title")
            if title_el:
                title = title_el.get_text(strip=True)
            else:
                title_tag = soup.find("title")
                if title_tag:
                    raw_title = title_tag.get_text(strip=True)
                    title = re.sub(r"\s*-\s*掘金$", "", raw_title)
            # Author
            author_el = soup.find("a", class_=re.compile(r"username"))
            if author_el:
                author = author_el.get_text(strip=True)
        except ImportError:
            # Regex fallback for title
            title_match = re.search(r'class="article-title"[^>]*>([^<]+)<', html)
            if title_match:
                title = title_match.group(1).strip()
            else:
                title_tag = re.search(r"<title>([^<]+)</title>", html)
                if title_tag:
                    raw_title = title_tag.group(1).strip()
                    title = re.sub(r"\s*-\s*掘金$", "", raw_title)
            # Regex fallback for author
            author_match = re.search(r'class="username[^"]*"[^>]*>([^<]+)<', html)
            if author_match:
                author = author_match.group(1).strip()

        # Extract article body HTML from the SSR-rendered content
        # The article content is in: <div class="article-viewer markdown-body cache result">...</div>
        body_html = self._extract_article_body(html)
        if not body_html:
            return {"success": False, "message": "Could not extract article content from page."}

        # Convert HTML to Markdown
        from markdownify import markdownify as md_convert
        mark_content = md_convert(
            body_html,
            heading_style="ATX",
            bullets="-",
            strip=["script", "style"],
        )

        # Clean up the markdown content
        mark_content = self._clean_markdown(mark_content)

        return self._write_markdown_file(
            title=title,
            mark_content=mark_content,
            article_id=article_id,
            author=author,
            ctime="",
            tags=[],
            output_dir=output_dir,
            download_images=download_images,
        )

    @staticmethod
    def _extract_article_body(html: str) -> str:
        """Extract the article body HTML from the SSR page.

        Uses BeautifulSoup if available, otherwise falls back to regex.
        """
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            # Primary: look for the markdown-body viewer
            viewer = soup.find("div", class_=re.compile(r"article-viewer"))
            if not viewer:
                # Fallback: look for article content
                viewer = soup.find("article") or soup.find("div", class_="article-content")
            if viewer:
                # Remove all <style> and <script> tags from the extracted content
                for tag in viewer.find_all(["style", "script"]):
                    tag.decompose()
                return str(viewer)
        except ImportError:
            pass

        # Regex fallback: strip inline <style> blocks first
        cleaned = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
        match = re.search(
            r'<div[^>]*class="[^"]*article-viewer[^"]*"[^>]*>(.*?)</div>\s*</div>\s*<div[^>]*class="[^"]*article-end',
            cleaned,
            re.DOTALL,
        )
        if match:
            return match.group(0)
        return ""

    @staticmethod
    def _fetch_page_with_playwright(url: str, timeout: int = 60000) -> str:
        """Use Playwright (headless Chromium) to load a page and return its HTML.

        This bypasses Juejin's WAF JS Challenge that blocks plain HTTP requests.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is required for web scraping. "
                "Install it with: pip install playwright && playwright install chromium"
            ) from exc

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                # Wait for the article content to appear (SSR content or JS-rendered)
                page.wait_for_selector(
                    "div.article-viewer, div.article-content, article",
                    timeout=30000,
                )
                # Give a small extra wait for full render
                page.wait_for_timeout(2000)
                html = page.content()
            except Exception:
                # If selector not found, still try to get whatever is on the page
                page.wait_for_timeout(5000)
                html = page.content()
            finally:
                browser.close()

        return html

    @staticmethod
    def _clean_markdown(text: str) -> str:
        """Clean up converted Markdown text."""
        # Remove excessive blank lines (more than 2 consecutive)
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        # Remove leading/trailing whitespace on each line but preserve indentation for code
        lines = text.split("\n")
        cleaned = []
        in_code_block = False
        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
            if not in_code_block:
                cleaned.append(line.rstrip())
            else:
                cleaned.append(line)
        return "\n".join(cleaned).strip()

    # ------------------------------------------------------------------ #
    #  Common: write markdown file
    # ------------------------------------------------------------------ #

    def _write_markdown_file(
        self,
        title: str,
        mark_content: str,
        article_id: str,
        author: str = "Unknown",
        ctime: str = "",
        tags: list[str] | None = None,
        output_dir: str = "./output",
        download_images: bool = False,
    ) -> dict[str, Any]:
        """Build the final Markdown content and write it to a file."""
        meta_lines = [
            f"# {title}",
            "",
            f"> Author: {author}",
        ]
        if ctime and ctime != "0":
            meta_lines.append(f"> Published: {timestamp_to_str(ctime)}")
        meta_lines.append(f"> Source: https://juejin.cn/post/{article_id}")
        if tags:
            meta_lines.append(f"> Tags: {', '.join(tags)}")
        meta_lines.append("")
        meta_lines.append("---")
        meta_lines.append("")

        full_md = "\n".join(meta_lines) + mark_content

        # Optionally download images
        if download_images:
            full_md = self._download_images(full_md, output_dir, article_id)

        # Write file
        ensure_dir(output_dir)
        safe_title = sanitize_filename(title)
        filepath = os.path.join(output_dir, f"{safe_title}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_md)

        return {"success": True, "filepath": filepath, "title": title}

    # ------------------------------------------------------------------ #
    #  Batch download by user
    # ------------------------------------------------------------------ #

    def download_user_articles(
        self,
        user_id_or_url: str,
        output_dir: str = "./output",
        max_count: int = 100,
        download_images: bool = False,
    ) -> list[dict[str, Any]]:
        """Download all (or up to *max_count*) articles from a user.

        Parameters
        ----------
        user_id_or_url : str
            A Juejin user profile URL or raw user ID.
        output_dir : str
            Base directory to write files.
        max_count : int
            Maximum number of articles to download.
        download_images : bool
            If ``True``, also download images.

        Returns
        -------
        list[dict]
            A list of result dicts, one per article.
        """
        user_id = extract_user_id(user_id_or_url)
        if not user_id:
            return [{"success": False, "message": f"Invalid user URL or ID: {user_id_or_url}"}]

        articles = self._fetch_user_article_list(user_id, max_count)
        if not articles:
            return [{"success": False, "message": "No articles found for this user."}]

        user_dir = os.path.join(output_dir, f"user_{user_id}")
        ensure_dir(user_dir)

        results: list[dict[str, Any]] = []
        for idx, art in enumerate(articles, 1):
            aid = art.get("article_id", "")
            title = art.get("title", "Untitled")
            print(f"[{idx}/{len(articles)}] Downloading: {title}")
            result = self.download_article(
                url_or_id=aid,
                output_dir=user_dir,
                download_images=download_images,
            )
            results.append(result)

        success_count = sum(1 for r in results if r.get("success"))
        print(f"\nDone. {success_count}/{len(articles)} articles saved to {user_dir}")
        return results

    # ------------------------------------------------------------------ #
    #  Get article detail
    # ------------------------------------------------------------------ #

    def get_article_detail(self, url_or_id: str) -> dict[str, Any] | None:
        """Fetch full article detail without saving to file.

        Useful for inspection or custom processing.
        """
        article_id = extract_article_id(url_or_id)
        if not article_id:
            return None
        return self._fetch_article_detail(article_id)

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _fetch_article_detail(self, article_id: str) -> dict[str, Any] | None:
        try:
            resp = self._api.post(ARTICLE_DETAIL_URL, json_body={"article_id": article_id})
            if resp.get("err_no") == 0:
                return resp.get("data", {})
        except Exception as exc:
            print(f"[Downloader] Error fetching article {article_id}: {exc}")
        return None

    def _fetch_user_article_list(
        self,
        user_id: str,
        max_count: int = 100,
    ) -> list[dict[str, Any]]:
        """Paginate through a user's articles."""
        all_articles: list[dict[str, Any]] = []
        cursor = "0"

        while len(all_articles) < max_count:
            body = {
                "user_id": user_id,
                "sort_type": 2,  # newest first
                "cursor": cursor,
                "limit": min(DEFAULT_PAGE_SIZE, max_count - len(all_articles)),
            }
            try:
                resp = self._api.post(ARTICLE_QUERY_LIST_URL, json_body=body)
            except Exception as exc:
                print(f"[Downloader] Error listing articles: {exc}")
                break

            data = resp.get("data", [])
            if not data:
                break

            for item in data:
                info = item.get("article_info", {})
                all_articles.append({
                    "article_id": info.get("article_id", ""),
                    "title": info.get("title", "Untitled"),
                })

            has_more = resp.get("has_more", False)
            cursor = resp.get("cursor", "0")
            if not has_more:
                break

        return all_articles[:max_count]

    def _download_images(self, md_text: str, output_dir: str, article_id: str) -> str:
        """Download images referenced in the Markdown and rewrite paths."""
        img_dir = os.path.join(output_dir, "images", article_id)
        ensure_dir(img_dir)

        # Match Markdown images: ![alt](url)
        pattern = r"!\[([^\]]*)\]\((https?://[^\)]+)\)"
        matches = re.findall(pattern, md_text)

        for idx, (alt, url) in enumerate(matches, 1):
            try:
                ext = self._guess_image_ext(url)
                filename = f"img_{idx}{ext}"
                local_path = os.path.join(img_dir, filename)
                relative_path = os.path.join("images", article_id, filename)

                resp = httpx.get(url, timeout=30, follow_redirects=True)
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(resp.content)

                md_text = md_text.replace(f"![{alt}]({url})", f"![{alt}]({relative_path})")
            except Exception as exc:
                print(f"[Downloader] Failed to download image {url}: {exc}")

        return md_text

    @staticmethod
    def _guess_image_ext(url: str) -> str:
        """Guess the image file extension from the URL."""
        lower = url.lower().split("?")[0]
        for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"):
            if lower.endswith(ext):
                return ext
        return ".png"
