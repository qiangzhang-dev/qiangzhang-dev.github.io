"""Offline mutation tests. Fixtures are temporary and never change website content."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from scripts.check_site import AIR_FUSION_AUTHORS, SITE_ORIGIN, check_site, main, page_url


def html(path, body="", head="", title=None, canonical=True):
    title = title or "Page " + path
    link = f'<link rel="canonical" href="{page_url(Path(path))}">' if canonical else ""
    if path == "index.html":
        head += f'<link rel="alternate" type="application/rss+xml" href="{SITE_ORIGIN}/feed.xml">'
        body += '<a href="/feed.xml">RSS</a>'
    return (f'<!doctype html><html><head><title>{title}</title>{link}{head}'
            f'</head><body>{body}</body></html>')


class SiteIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("index.html", html("index.html", '<a href="notes/example/#section">Note</a>'))
        self.write("notes/example/index.html", html("notes/example/index.html", '<h2 id="section">Section</h2>'))
        self.sitemap("/", "/notes/example/")
        self.write("feed.xml", f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>
<title>Technical notes</title><link>{SITE_ORIGIN}/#writing</link>
<description>中文技术笔记</description><language>zh-CN</language>
<atom:link href="{SITE_ORIGIN}/feed.xml" rel="self" type="application/rss+xml" />
<item><title>Example</title><link>{SITE_ORIGIN}/notes/example/</link>
<guid isPermaLink="true">{SITE_ORIGIN}/notes/example/</guid>
<description>A useful summary.</description></item></channel></rss>''')

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def mutate(self, relative, before, after):
        path = self.root / relative
        original = path.read_text(encoding="utf-8")
        self.assertIn(before, original)
        path.write_text(original.replace(before, after), encoding="utf-8")

    def sitemap(self, *paths):
        urls = "".join(f"<url><loc>{SITE_ORIGIN}{path}</loc></url>" for path in paths)
        self.write("sitemap.xml", '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + '</urlset>')

    def errors(self):
        return "\n".join(check_site(self.root).errors)

    def assert_clean(self):
        self.assertEqual(self.errors(), "")

    def test_valid_site_never_uses_network(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network prohibited")):
            self.assert_clean()

    def test_missing_path(self):
        self.mutate("index.html", "notes/example/#section", "notes/missing/")
        self.assertIn("missing local file", self.errors())

    def test_missing_anchor(self):
        self.mutate("index.html", "#section", "#absent")
        self.assertIn("missing anchor #absent", self.errors())

    def test_same_page_anchor(self):
        self.write("index.html", html("index.html", '<a href="#absent">Missing</a>'))
        self.assertIn("missing anchor #absent", self.errors())

    def test_relative_absolute_encoded_query_and_legacy_links(self):
        body = ('<h2 id="中文">Section</h2><a name="old"></a>'
                '<a href="#%E4%B8%AD%E6%96%87">Encoded</a><a href="#old">Old</a>'
                '<a href="../../?mode=1">Home</a><a href="?mode=1#中文">Self</a>'
                f'<a href="{SITE_ORIGIN}/notes/example/index.html#中文">Absolute</a>'
                '<a href="/notes/example/#top">Top</a><a href="#">Top</a>'
                '<a href="#中文:~:text=Section">Text fragment</a><a href="#:~:text=Section">Text</a>')
        self.write("notes/example/index.html", html("notes/example/index.html", body))
        self.mutate("index.html", "#section", "#中文")
        self.assert_clean()

    def test_protocol_relative_link_is_checked(self):
        self.mutate("index.html", "notes/example/#section", "//qiangzhang-dev.github.io/no-such-page/")
        self.assertIn("missing local file", self.errors())

    def test_local_assets_and_downloads(self):
        self.write("image.svg", "<svg/>")
        self.write("style.css", "body {}")
        self.write("data.json", "{}")
        body = '<img src="/image.svg"><a href="data.json#not-an-html-anchor">Download</a>'
        self.write("index.html", html("index.html", body, '<link rel="stylesheet" href="style.css">'))
        self.assert_clean()
        self.mutate("index.html", 'src="/image.svg"', 'src="/missing.svg"')
        self.assertIn("missing local file", self.errors())

    def test_external_links_and_explicit_project_route(self):
        body = ('<a href="https://example.com/missing#absent">External</a>'
                '<a href="mailto:hello@example.com">Email</a>'
                '<img src="data:image/svg+xml,abc">'
                '<a href="/subtracker/">Project</a>'
                '<a href="https://qiangzhang-dev.github.io/subtracker/#dashboard">Project</a>')
        self.write("index.html", html("index.html", body))
        result = check_site(self.root)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.external_route_links, 2)

    def test_project_exception_does_not_hide_nearby_typo(self):
        self.mutate("index.html", "notes/example/#section", "/subtracker-typo/")
        self.assertIn("missing local file", self.errors())

    def test_encoded_dot_segments_cannot_bypass_project_boundary(self):
        self.mutate("index.html", "notes/example/#section", "/subtracker/%2e%2e/missing/")
        self.assertIn("missing local file", self.errors())
        self.assertEqual(check_site(self.root).external_route_links, 0)

    def test_base_href_is_respected(self):
        self.write("index.html", html("index.html", '<a href="#section">Note</a>', '<base href="/notes/example/">'))
        self.assert_clean()

    def test_duplicate_title_across_pages(self):
        self.mutate("notes/example/index.html", "Page notes/example/index.html", "Page index.html")
        self.assertIn("duplicate title", self.errors())

    def test_duplicate_title_tag_in_one_head(self):
        self.mutate("index.html", "</title>", "</title><title>Second</title>")
        self.assertIn("exactly one nonempty head title", self.errors())

    def test_svg_title_does_not_count_as_document_title(self):
        self.mutate("index.html", "</body>", "<svg><title>Diagram</title></svg></body>")
        self.assert_clean()

    def test_duplicate_and_wrong_canonical(self):
        self.mutate("notes/example/index.html", SITE_ORIGIN + "/notes/example/", SITE_ORIGIN + "/")
        errors = self.errors()
        self.assertIn("duplicate canonical", errors)
        self.assertIn("canonical must be", errors)

    def test_missing_canonical(self):
        self.write("index.html", html("index.html", canonical=False))
        self.assertIn("exactly one canonical", self.errors())

    def test_multiple_canonicals_on_same_page(self):
        self.mutate("index.html", "</head>", f'<link rel="canonical" href="{SITE_ORIGIN}/"></head>')
        self.assertIn("exactly one canonical", self.errors())

    def test_missing_sitemap_entry(self):
        self.sitemap("/")
        self.assertIn("missing public page", self.errors())

    def test_new_report_is_discovered_without_updating_checker(self):
        self.write("experiments/new/report/index.html", html("experiments/new/report/index.html"))
        self.assertIn("missing public page " + SITE_ORIGIN + "/experiments/new/report/", self.errors())

    def test_stale_duplicate_and_nonpage_sitemap_urls(self):
        self.sitemap("/", "/notes/example/", "/", "/missing/", "/data.json")
        errors = self.errors()
        self.assertIn("duplicate URL entries", errors)
        self.assertIn("not an indexable local page: " + SITE_ORIGIN + "/missing/", errors)
        self.assertIn("not an indexable local page: " + SITE_ORIGIN + "/data.json", errors)

    def test_malformed_or_missing_sitemap_fails(self):
        self.write("sitemap.xml", "<urlset>")
        self.assertIn("sitemap.xml:", self.errors())
        (self.root / "sitemap.xml").unlink()
        self.assertIn("sitemap.xml:", self.errors())

    def test_excluded_fragment_and_hidden_or_dependency_files(self):
        for path in ("experiments/sft-explanation/followup/zhihu-article.html",
                     ".private/index.html", ".venv/index.html", "node_modules/pkg/index.html"):
            self.write(path, '<a href="/not-a-page/">Source fragment</a>')
        self.assert_clean()
        self.sitemap("/", "/notes/example/", "/experiments/sft-explanation/followup/zhihu-article.html")
        self.assertIn("not an indexable local page", self.errors())

    def test_noindex_page_links_checked_but_not_in_sitemap(self):
        self.write("draft.html", html("draft.html", '<a href="/">Home</a>', '<meta name="robots" content="noindex,follow">', canonical=False))
        self.assert_clean()
        self.mutate("draft.html", 'href="/"', 'href="/missing/"')
        self.assertIn("missing local file", self.errors())

    def add_citation(self):
        meta_names = [", ".join(reversed(name.split(" ", 1))) for name in AIR_FUSION_AUTHORS]
        head = "".join(f'<meta name="citation_author" content="{name}">' for name in meta_names)
        schema = {"@type": "ScholarlyArticle", "author": [{"@type": "Person", "name": name} for name in AIR_FUSION_AUTHORS]}
        head += '<script type="application/ld+json">' + json.dumps(schema) + '</script>'
        body = "<pre>author = {" + " and ".join(meta_names) + "}</pre>"
        self.write("air-fusion/index.html", html("air-fusion/index.html", body, head))
        self.sitemap("/", "/notes/example/", "/air-fusion/")

    def test_known_citation_matches_published_order(self):
        self.add_citation()
        self.assert_clean()

    def test_citation_metadata_mutation(self):
        self.add_citation()
        self.mutate("air-fusion/index.html", 'content="Cao, Bing"', 'content="Zhang, Qiang"')
        self.assertIn("citation_author differs from the published", self.errors())

    def test_structured_author_mutation(self):
        self.add_citation()
        self.mutate("air-fusion/index.html", '"name": "Bing Cao"', '"name": "Qiang Zhang"')
        self.assertIn("ScholarlyArticle differs from the published", self.errors())

    def test_bibtex_author_mutation(self):
        self.add_citation()
        self.mutate("air-fusion/index.html", "author = {Cao, Bing and Zhang, Qiang", "author = {Zhang, Qiang and Cao, Bing")
        self.assertIn("visible BibTeX differs from the published", self.errors())

    def test_missing_citation_metadata_is_detected(self):
        self.add_citation()
        self.write("air-fusion/index.html", html("air-fusion/index.html"))
        self.assertIn("missing or empty citation_author", self.errors())
        self.assertIn("requires one ScholarlyArticle", self.errors())

    def test_malformed_json_ld(self):
        self.add_citation()
        self.mutate("air-fusion/index.html", '"@type": "ScholarlyArticle"', 'invalid-json')
        self.assertIn("invalid JSON-LD", self.errors())

    def test_future_publication_not_constrained_to_air_fusion_authors(self):
        head = ('<meta name="citation_author" content="Another Author">'
                '<script type="application/ld+json">{"@type":"ScholarlyArticle",'
                '"author":{"name":"Another Author"}}</script>')
        self.write("paper/index.html", html("paper/index.html", head=head))
        self.sitemap("/", "/notes/example/", "/paper/")
        self.assert_clean()

    def test_cli_success_and_failure_exit_codes(self):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            self.assertEqual(main(["--root", str(self.root)]), 0)
            self.assertIn("PASS: 2 pages", out.getvalue())
            self.mutate("index.html", "#section", "#absent")
            self.assertEqual(main(["--root", str(self.root)]), 1)
            self.assertIn("missing anchor #absent", err.getvalue())


if __name__ == "__main__":
    unittest.main()
