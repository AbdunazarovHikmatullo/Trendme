from rest_framework import serializers

from parser.models import SourceDocument

from .models import SearchRun, TechnologyCandidate


class SourceDocumentSerializer(serializers.ModelSerializer):
    trust_level = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    class Meta:
        model = SourceDocument
        fields = (
            "title", "provider", "external_id", "source_name", "url",
            "published_date", "source_type", "role", "language", "trust", "trust_level",
        )

    def get_trust_level(self, item: SourceDocument) -> str:
        return "высокий" if item.trust >= 0.85 else "средний" if item.trust >= 0.6 else "пониженный"

    def get_role(self, item: SourceDocument) -> str:
        if item.source_type in {"academic", "preprint"}:
            return "core"
        if item.source_type == "patent":
            return "patent"
        if item.source_type == "encyclopedia":
            return "encyclopedia"
        return item.source_type


class CandidateSerializer(serializers.ModelSerializer):
    sources = SourceDocumentSerializer(source="source_documents", many=True, read_only=True)
    industry_label = serializers.CharField(source="get_industry_display", read_only=True)

    class Meta:
        model = TechnologyCandidate
        fields = ("id", "title", "description", "potential_benefit", "case_example", "confidence", "is_weak_signal", "is_high_confidence", "explanation", "factors", "industry", "industry_label", "sources")


class SearchRunSerializer(serializers.ModelSerializer):
    candidates = CandidateSerializer(many=True, read_only=True)

    class Meta:
        model = SearchRun
        fields = ("id", "query", "industry_filter", "status", "processed_sources", "candidates_count", "weak_signals_count", "high_confidence_count", "errors", "created_at", "started_at", "completed_at", "candidates")


class CreateSearchSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=300, min_length=2, trim_whitespace=True)
    industry = serializers.ChoiceField(
        choices=[
            ("industrial_ai", "Индустриальный ИИ"),
            ("robotics", "Робототехника"),
            ("infrastructure", "Инфраструктура ИИ"),
            ("fintech", "Финтех"),
            ("ai_security", "Защита ИИ"),
            ("edge", "Edge Computing"),
            ("semiconductor", "Полупроводники"),
            ("energy", "Энергетика"),
            ("health", "Здравоохранение"),
            ("other", "Другое"),
        ],
        required=False,
        allow_null=True,
        default=None,
    )
