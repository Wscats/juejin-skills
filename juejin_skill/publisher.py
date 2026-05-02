"""Publish Markdown articles to Juejin via the official API."""

from __future__ import annotations

import os
from typing import Any

from juejin_skill.api import JuejinAPI
from juejin_skill.config import (
    DRAFT_CREATE_URL,
    ARTICLE_PUBLISH_URL,
    CATEGORY_TAGS_URL,
    CATEGORY_BRIEFS_URL,
)


class ArticlePublisher:
    """Publish a Markdown article to Juejin.

    Workflow
    --------
    1. Create a draft via the ``article_draft/create`` API.
    2. Publish the draft via the ``article/publish`` API.

    A valid cookie is required. Use :class:`juejin_skill.auth.JuejinAuth`
    to obtain one.
    """

    def __init__(self, cookie: str = "") -> None:
        if not cookie:
            raise ValueError("A valid cookie is required to publish articles. Please login first.")
        self._api = JuejinAPI(cookie=cookie)

    # ------------------------------------------------------------------ #
    #  Main publish entry
    # ------------------------------------------------------------------ #

    def publish_markdown(
        self,
        filepath: str = "",
        content: str = "",
        title: str = "",
        category_id: str = "",
        tag_ids: list[str] | None = None,
        brief_content: str = "",
        cover_image: str = "",
        save_draft_only: bool = True,
        allow_public_publish: bool = False,
    ) -> dict[str, Any]:
        """Create a draft on Juejin, or (opt-in) publish it publicly.

        **Safe-by-default contract**

        This method always creates a draft. A public publish ONLY happens
        when **both** of the following are true:

        * ``save_draft_only=False`` (caller opts out of the safe default), and
        * ``allow_public_publish=True`` (explicit, human-reviewed intent).

        This two-flag interlock exists so that automated agents cannot
        accidentally publish to the user's Juejin account by forgetting a
        single keyword argument. Earlier versions defaulted
        ``save_draft_only=False``, which ClawScan correctly flagged as an
        unsafe default at the API layer (Tool Misuse and Exploitation).

        Either *filepath* or *content* (with *title*) must be provided.

        Parameters
        ----------
        filepath : str
            Path to a ``.md`` file. The first ``# heading`` is used as title.
        content : str
            Raw Markdown string (used when *filepath* is empty).
        title : str
            Article title (overrides the heading extracted from *filepath*).
        category_id : str
            Category ID (e.g. ``"6809637767543259144"`` for frontend).
        tag_ids : list[str] | None
            A list of tag IDs to attach. Use :meth:`search_tags` to find IDs.
        brief_content : str
            Article summary / abstract (max ~100 chars recommended).
        cover_image : str
            URL of the cover image.
        save_draft_only : bool
            If ``True`` (default), only create a draft - nothing is published
            to the public feed.
        allow_public_publish : bool
            Required safety interlock. Must be explicitly set to ``True`` by
            the caller when ``save_draft_only=False``, otherwise this method
            refuses to publish and stays in draft-only mode.

        Returns
        -------
        dict
            API response dict containing ``article_id`` (or ``draft_id``).
        """
        # Resolve content from file
        if filepath:
            title_from_file, md_content = self._read_markdown_file(filepath)
            if not title:
                title = title_from_file
            content = md_content

        if not title:
            raise ValueError("Article title is required.")
        if not content:
            raise ValueError("Article content is required.")

        # Auto-generate brief if not provided
        if not brief_content:
            plain = content.replace("#", "").replace("*", "").replace("`", "").strip()
            brief_content = plain[:100]

        # ---- Safety interlock --------------------------------------------------
        # Refuse to publish publicly unless the caller explicitly opted in on
        # both flags. This is the single source of truth for the draft-only
        # policy advertised in SKILL.md.
        publish_publicly = (not save_draft_only) and bool(allow_public_publish)
        if (not save_draft_only) and (not allow_public_publish):
            return {
                "success": False,
                "message": (
                    "Refusing to publish: save_draft_only=False was passed but "
                    "allow_public_publish=True was not. Public publishing requires "
                    "explicit human-reviewed intent via both flags."
                ),
                "policy": "draft-only-by-default",
            }

        # Step 1: create draft
        draft_data = self._create_draft(
            title=title,
            content=content,
            category_id=category_id,
            tag_ids=tag_ids or [],
            brief_content=brief_content,
            cover_image=cover_image,
        )

        draft_id = (draft_data.get("data") or {}).get("id", "")
        if not draft_id:
            return {"success": False, "message": "Failed to create draft", "raw": draft_data}

        if not publish_publicly:
            return {
                "success": True,
                "message": f"Draft created successfully (draft_id={draft_id})",
                "draft_id": draft_id,
            }

        # Step 2: publish
        publish_data = self._publish_article(
            draft_id=draft_id,
            category_id=category_id,
            tag_ids=tag_ids or [],
            cover_image=cover_image,
            brief_content=brief_content,
        )

        article_id = (publish_data.get("data") or {}).get("article_id", "")
        if article_id:
            return {
                "success": True,
                "message": f"Article published! https://juejin.cn/post/{article_id}",
                "article_id": article_id,
                "url": f"https://juejin.cn/post/{article_id}",
            }
        return {"success": False, "message": "Publish failed", "raw": publish_data}

    # ------------------------------------------------------------------ #
    #  Tag / category helpers
    # ------------------------------------------------------------------ #

    def get_categories(self) -> list[dict[str, Any]]:
        """List available article categories."""
        resp = self._api.get(CATEGORY_BRIEFS_URL)
        return [
            {"category_id": c.get("category_id"), "category_name": c.get("category_name")}
            for c in resp.get("data", [])
        ]

    def search_tags(self, category_id: str, keyword: str = "", limit: int = 50) -> list[dict[str, Any]]:
        """Search for tags under a category.

        Parameters
        ----------
        category_id : str
            Category to search in.
        keyword : str
            Optional keyword filter (client-side).
        limit : int
            Max number of tags.

        Returns
        -------
        list[dict]
            Tags with ``tag_id`` and ``tag_name``.
        """
        body = {"cate_id": category_id, "cursor": "0", "limit": limit}
        resp = self._api.post(CATEGORY_TAGS_URL, json_body=body)
        tags = resp.get("data", [])
        result = []
        for t in tags:
            # The recommend_tag_list API returns tag_id/tag_name at top level
            tag_id = t.get("tag_id", "")
            tag_name = t.get("tag_name", "")
            if tag_id and tag_name:
                result.append({"tag_id": tag_id, "tag_name": tag_name})
        if keyword:
            kw = keyword.lower()
            result = [t for t in result if kw in t["tag_name"].lower()]
        return result

    # ------------------------------------------------------------------ #
    #  Internal API calls
    # ------------------------------------------------------------------ #

    def _create_draft(
        self,
        title: str,
        content: str,
        category_id: str,
        tag_ids: list[str],
        brief_content: str,
        cover_image: str,
    ) -> dict[str, Any]:
        body = {
            "category_id": category_id,
            "tag_ids": tag_ids,
            "link_url": "",
            "cover_image": cover_image,
            "title": title,
            "brief_content": brief_content,
            "edit_type": 10,  # 10 = Markdown editor
            "html_content": "deprecated",
            "mark_content": content,
            "theme_ids": [],
        }
        return self._api.post(DRAFT_CREATE_URL, json_body=body)

    def _publish_article(
        self,
        draft_id: str,
        category_id: str,
        tag_ids: list[str],
        cover_image: str,
        brief_content: str,
    ) -> dict[str, Any]:
        body = {
            "draft_id": draft_id,
            "sync_to_org": False,
            "column_ids": [],
            "theme_ids": [],
            "encrypted_word_count": 0,
            "category_id": category_id,
            "tag_ids": tag_ids,
            "cover_image": cover_image,
            "brief_content": brief_content,
        }
        return self._api.post(ARTICLE_PUBLISH_URL, json_body=body)

    # ------------------------------------------------------------------ #
    #  Markdown file reading
    # ------------------------------------------------------------------ #

    @staticmethod
    def _read_markdown_file(filepath: str) -> tuple[str, str]:
        """Read a Markdown file and extract (title, body).

        The title is taken from the first ``# heading`` line.
        """
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Markdown file not found: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read()

        lines = raw.split("\n")
        title = ""
        body_start = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("##"):
                title = stripped.lstrip("# ").strip()
                body_start = i + 1
                break

        body = "\n".join(lines[body_start:]).strip()
        return title, body if body else raw
