from django.test import SimpleTestCase

from .services import _arxiv_query, _extract_patent_id, _parse_html_date, _parse_html_section


class SourceQueryTests(SimpleTestCase):
    def test_translates_known_russian_terms_for_arxiv(self) -> None:
        self.assertEqual(_arxiv_query("квантовые сенсоры"), "all:quantum AND all:sensor")


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
