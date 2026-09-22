from django.test import SimpleTestCase

from .services import _arxiv_query


class SourceQueryTests(SimpleTestCase):
    def test_translates_known_russian_terms_for_arxiv(self) -> None:
        self.assertEqual(_arxiv_query("квантовые сенсоры"), "all:quantum AND all:sensor")
