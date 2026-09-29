from django.test import SimpleTestCase

from .services import (
    _arxiv_query,
    _extract_patent_id,
    _parse_html_date,
    _parse_html_section,
    _strip_markup,
    build_google_patents_url,
    english_search_query,
)


class SourceQueryTests(SimpleTestCase):
    def test_translates_known_russian_terms_for_arxiv(self) -> None:
        self.assertIn("all:quantum", _arxiv_query("квантовые сенсоры"))
        self.assertIn("all:sensor", _arxiv_query("квантовые сенсоры"))

    def test_english_search_query_expands_russian_stems(self) -> None:
        self.assertEqual(english_search_query("квантовые сенсоры"), "quantum sensor")
        self.assertEqual(english_search_query("робототехника"), "robot")
        self.assertEqual(english_search_query("Искусственный интеллект"), "artificial intelligence")
        self.assertEqual(english_search_query("нейроморфные процессоры"), "neuromorphic processor")
        self.assertEqual(english_search_query("перовскитные солнечные элементы"), "perovskite solar")
        self.assertEqual(english_search_query("твердотельные батареи"), "solid-state battery")
        self.assertEqual(english_search_query("твёрдотельные батареи"), "solid-state battery")

    def test_untranslated_cyrillic_query_is_empty(self) -> None:
        self.assertEqual(english_search_query("топологические изоляторы"), "")
        self.assertEqual(_arxiv_query("топологические изоляторы"), "")


class GooglePatentsUrlTests(SimpleTestCase):
    def test_uses_xhr_json_endpoint_without_double_q(self) -> None:
        url = build_google_patents_url("quantum sensor", limit=10)
        self.assertIn("patents.google.com/xhr/query", url)
        self.assertNotIn("q=q=", url)
        self.assertIn("exp=", url)

    def test_strips_google_highlight_tags(self) -> None:
        self.assertEqual(_strip_markup("NV <b>quantum sensor</b> &hellip;"), "NV quantum sensor ...")


class PatentExtractionTests(SimpleTestCase):
    def test_extract_patent_id_from_url(self) -> None:
        url = "https://patents.google.com/patent/US12345678B2/en"
        self.assertEqual(_extract_patent_id(url), "12345678")

    def test_extract_patent_id_from_numbered_url(self) -> None:
        url = "https://patents.google.com/patent/US2023123456A1/en"
        self.assertEqual(_extract_patent_id(url), "2023123456")

    def test_extract_patent_id_from_short_url(self) -> None:
        url = "https://patents.google.com/patent/US12345678B2"
        self.assertEqual(_extract_patent_id(url), "12345678")

    def test_parse_html_section_abstract(self) -> None:
        html = '<div id="abstract"><p>This is an abstract text about quantum computing.</p></div>'
        result = _parse_html_section(html, "abstract")
        self.assertIn("quantum", result.lower())
        self.assertNotIn("<", result)

    def test_parse_html_section_missing(self) -> None:
        html = '<div id="description">Some description</div>'
        result = _parse_html_section(html, "abstract")
        self.assertEqual(result, "")

    def test_parse_html_date_iso_format(self) -> None:
        html = '{"datePublished": "2024-03-15"}'
        result = _parse_html_date(html)
        self.assertEqual(result, "2024-03-15")

    def test_parse_html_date_meta_tag(self) -> None:
        html = '<meta name="date" content="2024-06-20">'
        result = _parse_html_date(html)
        self.assertEqual(result, "2024-06-20")

    def test_parse_html_date_text_format(self) -> None:
        html = "Published: 2024 January 10"
        result = _parse_html_date(html)
        self.assertEqual(result, "2024-01-10")

    def test_parse_html_date_missing(self) -> None:
        html = "<p>No date information here</p>"
        result = _parse_html_date(html)
        self.assertIsNone(result)
