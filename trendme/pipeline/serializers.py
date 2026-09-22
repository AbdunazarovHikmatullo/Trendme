from rest_framework import serializers

from parser.models import SourceDocument

from .models import SearchRun, TechnologyCandidate


class SourceDocumentSerializer(serializers.ModelSerializer):
    trust_level = serializers.SerializerMethodField()

    class Meta:
        model = SourceDocument
        fields = ("source_name", "url", "published_date", "source_type", "language", "trust", "trust_level")

    def get_trust_level(self, item: SourceDocument) -> str:
        return "высокий" if item.trust >= 0.85 else "средний" if item.trust >= 0.6 else "пониженный"


class CandidateSerializer(serializers.ModelSerializer):
    sources = SourceDocumentSerializer(source="source_documents", many=True, read_only=True)

    class Meta:
        model = TechnologyCandidate
        fields = ("id", "title", "description", "potential_benefit", "case_example", "confidence", "is_weak_signal", "is_high_confidence", "explanation", "factors", "sources")


class SearchRunSerializer(serializers.ModelSerializer):
    candidates = CandidateSerializer(many=True, read_only=True)

    class Meta:
        model = SearchRun
        fields = ("id", "query", "status", "processed_sources", "candidates_count", "weak_signals_count", "high_confidence_count", "errors", "created_at", "started_at", "completed_at", "candidates")


class CreateSearchSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=300, min_length=2, trim_whitespace=True)
