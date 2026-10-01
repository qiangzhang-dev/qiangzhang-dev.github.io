#!/usr/bin/env python3
"""Check the plain GitHub Pages source tree without network or dependencies."""

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
import sys
from urllib.parse import quote, unquote, urljoin, urlsplit
import xml.etree.ElementTree as ET

SITE_ORIGIN = "https://qiangzhang-dev.github.io"
# This is a preserved publication fragment, not a standalone website page.
EXCLUDED_HTML = {
    "experiments/sft-explanation/followup/zhihu-article.html":
        "Zhihu publication source; see the adjacent README",
}
# GitHub Pages serves this project from a different repository on the same host.
EXTERNAL_ROUTES = {"/subtracker": "qiangzhang-dev/subtracker"}
IGNORED_DIRS = {"node_modules", "__pycache__", "venv"}
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
ATOM_NS = "http://www.w3.org/2005/Atom"
FEED_URL = SITE_ORIGIN + "/feed.xml"
# Published order: https://www.ijcai.org/proceedings/2026/105
# Scoped to this paper only; future publications have their own author lists.
AIR_FUSION_AUTHORS = ("Bing Cao", "Qiang Zhang", "Xingxin Xu", "Pengfei Zhu")


def clean(value):
    return " ".join(value.split())


def page_url(relative):
    path = relative.as_posix()
    if path == "index.html":
        path = ""
    elif path.endswith("/index.html"):
        path = path[:-len("index.html")]
    return SITE_ORIGIN + "/" + quote(path, safe="/")


class Page(HTMLParser):
    def __init__(self, relative, source):
        super().__init__(convert_charrefs=True)
        self.relative = relative
        self.url = page_url(relative)
        self.anchors = set()
        self.links = []
        self.titles = []
        self.canonicals = []
        self.feed_links = []
        self.body_links = []
        self.meta = defaultdict(list)
        self.json_ld = []
        self.text = []
        self.base = None
        self._head = False
        self._title = None
        self._json = None
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "head":
            self._head = True
        if attrs.get("id"):
            self.anchors.add(attrs["id"])
        if tag == "a" and attrs.get("name"):
            self.anchors.add(attrs["name"])
        if tag == "base":
            if self.base is None and "href" in attrs:
                self.base = attrs["href"]
        else:
            for name in ("href", "src", "poster"):
                if name in attrs:
                    self.links.append((attrs[name] or "", self.getpos()[0]))
        if self._head:
            if tag == "title":
                self._title = []
            if tag == "link" and "canonical" in attrs.get("rel", "").lower().split():
                self.canonicals.append(attrs.get("href", ""))
            if tag == "link" and "alternate" in attrs.get("rel", "").lower().split() and attrs.get("type") == "application/rss+xml":
                self.feed_links.append(attrs.get("href", ""))
            if tag == "meta" and attrs.get("name"):
                self.meta[attrs["name"].lower()].append(attrs.get("content", ""))
        elif tag == "a":
            self.body_links.append(attrs.get("href", ""))
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self._json = []

    def handle_endtag(self, tag):
        if tag == "title" and self._title is not None:
            self.titles.append(clean("".join(self._title)))
            self._title = None
        if tag == "head":
            self._head = False
        if tag == "script" and self._json is not None:
            self.json_ld.append("".join(self._json))
            self._json = None

    def handle_data(self, data):
        if self._title is not None:
            self._title.append(data)
        if self._json is not None:
            self._json.append(data)
        self.text.append(data)

    @property
    def noindex(self):
        directives = ",".join(self.meta["robots"]).lower()
        return bool({"noindex", "none"} & set(re.split(r"[\s,]+", directives)))


def external_route(path):
    return any(path == prefix or path.startswith(prefix + "/")
               for prefix in EXTERNAL_ROUTES)


def local_target(root, url):
    """Return (file, fragment, separate_repository) for an internal HTTP URL."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != urlsplit(SITE_ORIGIN).netloc:
        return None, "", False
    path = posixpath.normpath("/" + unquote(parsed.path).lstrip("/"))
    if external_route(path):
        return None, "", True
    target = (root / path.lstrip("/")).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"local URL escapes the site root: {url}")
    if parsed.path.endswith("/") or target.is_dir():
        target /= "index.html"
    return target, unquote(parsed.fragment).split(":~:text=", 1)[0], False


def scholarly_nodes(value):
    if isinstance(value, dict):
        types = value.get("@type", [])
        if "ScholarlyArticle" in ([types] if isinstance(types, str) else types):
            yield value
        for item in value.values():
            yield from scholarly_nodes(item)
    elif isinstance(value, list):
        for item in value:
            yield from scholarly_nodes(item)


def author_name(value):
    # The site's Highwire/BibTeX names use "Family, Given"; JSON-LD uses "Given Family".
    parts = value.split(",", 1)
    return clean(" ".join(reversed(parts)) if len(parts) == 2 else value).casefold()


def citation_errors(page):
    if page.relative.as_posix() != "air-fusion/index.html":
        return []
    errors, articles = [], []
    for raw in page.json_ld:
        try:
            articles.extend(scholarly_nodes(json.loads(raw)))
        except (ValueError, TypeError):
            errors.append("invalid JSON-LD")
    authors = page.meta["citation_author"]
    if not authors or any(not clean(name) for name in authors):
        errors.append("missing or empty citation_author metadata")
    if len(articles) != 1:
        errors.append("citation metadata requires one ScholarlyArticle JSON-LD record")
        return errors
    structured = articles[0].get("author", [])
    if isinstance(structured, dict):
        structured = [structured]
    names = [author_name(item.get("name", "")) if isinstance(item, dict) else ""
             for item in structured] if isinstance(structured, list) else []
    expected = [author_name(name) for name in AIR_FUSION_AUTHORS]
    if [author_name(name) for name in authors] != expected:
        errors.append("citation_author differs from the published AIR-Fusion author order/names")
    if not names or not all(names) or names != expected:
        errors.append("ScholarlyArticle differs from the published AIR-Fusion author order/names")
    # Deliberately small: this site's visible BibTeX uses plain, brace-delimited names.
    match = re.search(r"\bauthor\s*=\s*\{([^{}]+)\}", "".join(page.text), re.I)
    if not match or [author_name(name) for name in re.split(r"\s+and\s+", match[1])] != expected:
        errors.append("visible BibTeX differs from the published AIR-Fusion author order/names")
    return errors


@dataclass
class Result:
    errors: list = field(default_factory=list)
    page_count: int = 0
    local_links: int = 0
    external_route_links: int = 0
    feed_items: int = 0


def check_feed(root, pages, result):
    """Validate this site's curated RSS notes feed, not every sitemap page."""
    homepage = pages.get(root / "index.html")
    if homepage:
        base = urljoin(homepage.url, homepage.base) if homepage.base is not None else homepage.url
        if [urljoin(base, href) for href in homepage.feed_links] != [FEED_URL]:
            result.errors.append("index.html: expected one head RSS autodiscovery link to feed.xml")
        if FEED_URL not in [urljoin(base, href) for href in homepage.body_links]:
            result.errors.append("index.html: missing body link to feed.xml")
    try:
        rss = ET.parse(root / "feed.xml").getroot()
        if rss.tag != "rss" or rss.get("version") != "2.0" or len(rss.findall("channel")) != 1:
            raise ValueError("expected RSS 2.0 with exactly one channel")
        channel = rss.find("channel")
    except (OSError, ET.ParseError, ValueError) as error:
        result.errors.append(f"feed.xml: {error}")
        return

    def text_field(node, tag, label):
        fields = node.findall(tag)
        if len(fields) != 1 or len(fields[0]) or not clean(fields[0].text or ""):
            result.errors.append(f"feed.xml: {label} requires one nonempty plain-text {tag}")
            return ""
        return clean(fields[0].text)

    for tag in ("title", "description", "language"):
        text_field(channel, tag, "channel")
    if text_field(channel, "link", "channel") != SITE_ORIGIN + "/#writing":
        result.errors.append("feed.xml: channel link must point to the homepage writing section")
    self_links = [node for node in channel.findall(f"{{{ATOM_NS}}}link") if node.get("rel") == "self"]
    if len(self_links) != 1 or self_links[0].get("href") != FEED_URL or self_links[0].get("type") != "application/rss+xml":
        result.errors.append("feed.xml: expected one RSS atom:self link to the canonical feed URL")
    items = channel.findall("item")
    result.feed_items = len(items)
    if not items:
        result.errors.append("feed.xml: no article items")
    links, guids = set(), set()
    for number, item in enumerate(items, 1):
        label = f"item {number}"
        for tag in ("title", "description"):
            text_field(item, tag, label)
        link = text_field(item, "link", label)
        guid = text_field(item, "guid", label)
        if link in links or guid in guids:
            result.errors.append(f"feed.xml: {label} duplicates an article link or GUID")
        links.add(link)
        guids.add(guid)
        guid_nodes = item.findall("guid")
        if guid != link or len(guid_nodes) != 1 or guid_nodes[0].get("isPermaLink") != "true":
            result.errors.append(f"feed.xml: {label} GUID must be its canonical permalink")
        target, _, separate = local_target(root, link)
        page = pages.get(target)
        # Only top-level authored notes: nested reports, utilities and project pages
        # are supporting resources, not additional entries in this feed.
        if (separate or page is None or page.noindex or link != page.url
                or len(page.relative.parts) != 3 or page.relative.parts[0] != "notes"
                or page.relative.name != "index.html" or page.canonicals != [link]):
            result.errors.append(f"feed.xml: {label} link must be an indexable authored note's canonical URL: {link!r}")
        dates = item.findall("pubDate")
        if len(dates) > 1:
            result.errors.append(f"feed.xml: {label} has duplicate pubDate elements")
        for date in dates:
            try:
                parsed = parsedate_to_datetime(date.text or "")
                if parsed.tzinfo is None or len(date):
                    raise ValueError("missing time zone or not plain text")
            except (TypeError, ValueError, OverflowError):
                result.errors.append(f"feed.xml: {label} pubDate must be a valid RSS date with time zone")


def check_site(root):
    root = Path(root).resolve()
    result = Result()
    pages = {}
    for path in sorted(root.rglob("*.html")):
        relative = path.relative_to(root)
        if (any(part.startswith(".") or part in IGNORED_DIRS for part in relative.parts)
                or relative.as_posix() in EXCLUDED_HTML):
            continue
        pages[path.resolve()] = Page(relative, path.read_text(encoding="utf-8"))
    result.page_count = len(pages)
    if root / "index.html" not in pages:
        result.errors.append("index.html: missing site homepage")
    titles, canonicals = defaultdict(list), defaultdict(list)
    expected_sitemap = set()
    for path, page in pages.items():
        prefix = str(page.relative)
        if len(page.titles) != 1 or not page.titles[0]:
            result.errors.append(f"{prefix}: expected exactly one nonempty head title")
        else:
            titles[page.titles[0]].append(prefix)
        if not page.noindex:
            expected_sitemap.add(page.url)
        if len(page.canonicals) != 1 and not (page.noindex and not page.canonicals):
            result.errors.append(f"{prefix}: expected exactly one canonical link")
        for canonical in page.canonicals:
            canonicals[canonical].append(prefix)
            if canonical != page.url:
                result.errors.append(f"{prefix}: canonical must be {page.url}, got {canonical!r}")
        result.errors.extend(f"{prefix}: {error}" for error in citation_errors(page))
        base = urljoin(page.url, page.base) if page.base is not None else page.url
        for link, line in page.links:
            target, fragment, separate = local_target(root, urljoin(base, link))
            if separate:
                result.external_route_links += 1
                continue
            if target is None:
                continue
            result.local_links += 1
            location = f"{prefix}:{line}"
            if not target.is_file():
                result.errors.append(f"{location}: missing local file for {link!r}")
            elif fragment and target.suffix.lower() == ".html":
                target_page = pages.get(target)
                if target_page is None:
                    target_page = Page(target.relative_to(root), target.read_text(encoding="utf-8"))
                if fragment not in target_page.anchors and fragment.lower() != "top":
                    result.errors.append(f"{location}: missing anchor #{fragment} for {link!r}")
    for label, values in (("title", titles), ("canonical", canonicals)):
        for value, owners in values.items():
            if len(owners) > 1:
                result.errors.append(f"duplicate {label} {value!r}: {', '.join(owners)}")
    try:
        sitemap = ET.parse(root / "sitemap.xml").getroot()
        if sitemap.tag != f"{{{SITEMAP_NS}}}urlset":
            raise ValueError("expected a sitemap urlset with the standard namespace")
        locations = [clean(node.text or "")
                     for node in sitemap.findall(f"{{{SITEMAP_NS}}}url/{{{SITEMAP_NS}}}loc")]
        if len(locations) != len(set(locations)):
            result.errors.append("sitemap.xml: duplicate URL entries")
        for missing in sorted(expected_sitemap - set(locations)):
            result.errors.append(f"sitemap.xml: missing public page {missing}")
        for extra in sorted(set(locations) - expected_sitemap):
            result.errors.append(f"sitemap.xml: URL is not an indexable local page: {extra}")
    except (OSError, ET.ParseError, ValueError) as error:
        result.errors.append(f"sitemap.xml: {error}")
    check_feed(root, pages, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="site source root (default: this script's repository)")
    args = parser.parse_args(argv)
    try:
        result = check_site(args.root)
    except (OSError, ValueError) as error:
        print(f"Site check failed: {error}", file=sys.stderr)
        return 1
    if result.errors:
        for error in result.errors:
            print(error, file=sys.stderr)
        print(f"FAIL: {len(result.errors)} issue(s)", file=sys.stderr)
        return 1
    print(f"PASS: {result.page_count} pages, {result.local_links} local references; "
          f"{result.feed_items} RSS items; {result.external_route_links} separate-repository route(s) skipped. No network requests.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
