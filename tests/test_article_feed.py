"""Focused mutation tests for the curated RSS feed and its discovery links."""

from copy import deepcopy
from datetime import datetime, timezone
from email.utils import format_datetime
import unittest
import xml.etree.ElementTree as ET

from scripts.check_site import SITE_ORIGIN, check_site
import test_site_integrity as fixtures


class ArticleFeedTests(unittest.TestCase):
    # Reuse fixture helpers, without inheriting/rerunning unrelated test methods.
    setUp = fixtures.SiteIntegrityTests.setUp
    write = fixtures.SiteIntegrityTests.write
    mutate = fixtures.SiteIntegrityTests.mutate
    sitemap = fixtures.SiteIntegrityTests.sitemap
    errors = fixtures.SiteIntegrityTests.errors
    assert_clean = fixtures.SiteIntegrityTests.assert_clean

    def edit_feed(self, change):
        rss = ET.parse(self.root / "feed.xml").getroot()
        change(rss)
        ET.ElementTree(rss).write(self.root / "feed.xml", encoding="utf-8", xml_declaration=True)

    def test_valid_feed_without_dates(self):
        result = check_site(self.root)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.feed_items, 1)

    def test_missing_or_malformed_feed(self):
        self.write("feed.xml", "<rss>")
        self.assertIn("feed.xml:", self.errors())
        (self.root / "feed.xml").unlink()
        self.assertIn("feed.xml:", self.errors())

    def test_wrong_rss_version_and_duplicate_channel(self):
        self.edit_feed(lambda rss: rss.set("version", "0.91"))
        self.assertIn("expected RSS 2.0", self.errors())
        self.edit_feed(lambda rss: rss.set("version", "2.0"))
        self.edit_feed(lambda rss: rss.append(deepcopy(rss.find("channel"))))
        self.assertIn("exactly one channel", self.errors())

    def test_missing_channel_metadata_and_wrong_channel_link(self):
        self.edit_feed(lambda rss: rss.find("channel").remove(rss.find("channel/title")))
        self.assertIn("channel requires one nonempty plain-text title", self.errors())
        self.mutate("feed.xml", SITE_ORIGIN + "/#writing", "https://example.com/")
        self.assertIn("channel link must point", self.errors())

    def test_wrong_or_missing_self_link(self):
        self.mutate("feed.xml", 'href="' + SITE_ORIGIN + '/feed.xml"', 'href="https://example.com/feed.xml"')
        self.assertIn("atom:self link", self.errors())

    def test_empty_feed(self):
        self.edit_feed(lambda rss: rss.find("channel").remove(rss.find("channel/item")))
        self.assertIn("no article items", self.errors())

    def test_empty_title_or_summary(self):
        self.mutate("feed.xml", "<title>Example</title>", "<title>  </title>")
        self.mutate("feed.xml", "<description>A useful summary.</description>", "<description />")
        errors = self.errors()
        self.assertIn("item 1 requires one nonempty plain-text title", errors)
        self.assertIn("item 1 requires one nonempty plain-text description", errors)

    def test_duplicate_article(self):
        self.edit_feed(lambda rss: rss.find("channel").append(deepcopy(rss.find("channel/item"))))
        self.assertIn("duplicates an article link or GUID", self.errors())

    def test_wrong_guid(self):
        self.mutate("feed.xml", 'isPermaLink="true"', 'isPermaLink="false"')
        self.assertIn("GUID must be its canonical permalink", self.errors())

    def test_noncanonical_missing_and_external_urls(self):
        original = (self.root / "feed.xml").read_text(encoding="utf-8")
        for destination in (SITE_ORIGIN + "/notes/example/index.html",
                            SITE_ORIGIN + "/notes/example/#section",
                            SITE_ORIGIN + "/notes/missing/",
                            "https://example.com/notes/example/"):
            with self.subTest(destination=destination):
                self.write("feed.xml", original.replace(SITE_ORIGIN + "/notes/example/", destination))
                self.assertIn("indexable authored note's canonical URL", self.errors())

    def test_supporting_report_is_not_an_extra_article(self):
        self.write("notes/example/report/index.html", fixtures.html("notes/example/report/index.html"))
        self.sitemap("/", "/notes/example/", "/notes/example/report/")
        self.assert_clean()  # Sitemap pages do not all need to be RSS items.
        self.mutate("feed.xml", SITE_ORIGIN + "/notes/example/", SITE_ORIGIN + "/notes/example/report/")
        self.assertIn("indexable authored note's canonical URL", self.errors())

    def test_noindex_note_cannot_appear_in_feed(self):
        self.write("notes/example/index.html", fixtures.html("notes/example/index.html", '<h2 id="section">Section</h2>', '<meta name="robots" content="noindex">'))
        self.sitemap("/")
        self.assertIn("indexable authored note's canonical URL", self.errors())

    def test_unicode_and_escaped_xml_text(self):
        self.mutate("feed.xml", "A useful summary.", "条件 A &amp; B：x &lt; y，保留中文。")
        self.assert_clean()
        summary = ET.parse(self.root / "feed.xml").findtext("channel/item/description")
        self.assertEqual(summary, "条件 A & B：x < y，保留中文。")

    def test_optional_dates_require_valid_rss_syntax_and_timezone(self):
        self.edit_feed(lambda rss: ET.SubElement(rss.find("channel/item"), "pubDate"))
        for value in ("2026-09-29", "Tue, 29 Sep 2026 12:00:00", "invalid"):
            with self.subTest(date=value):
                self.edit_feed(lambda rss: setattr(rss.find("channel/item/pubDate"), "text", value))
                self.assertIn("valid RSS date with time zone", self.errors())
        value = format_datetime(datetime(2026, 9, 29, 12, tzinfo=timezone.utc), usegmt=True)
        self.edit_feed(lambda rss: setattr(rss.find("channel/item/pubDate"), "text", value))
        self.assert_clean()

    def test_missing_autodiscovery_and_body_link(self):
        self.mutate("index.html", 'type="application/rss+xml"', 'type="text/plain"')
        self.mutate("index.html", '<a href="/feed.xml">RSS</a>', "")
        errors = self.errors()
        self.assertIn("head RSS autodiscovery", errors)
        self.assertIn("missing body link", errors)

    def test_relative_autodiscovery_is_valid(self):
        self.mutate("index.html", SITE_ORIGIN + "/feed.xml", "/feed.xml")
        self.assert_clean()


if __name__ == "__main__":
    unittest.main()
