from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SearchRun, TechnologyCandidate
from .serializers import CreateSearchSerializer, SearchRunSerializer
from .tasks import start_search


class SearchCollectionView(APIView):
    def post(self, request):
        serializer = CreateSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = SearchRun.objects.create(query=serializer.validated_data["query"])
        start_search.delay(str(run.id))
        return Response(SearchRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    def get(self, request):
        """Возвращает список всех запусков с фильтрацией по категории."""
        category = request.query_params.get("category", "all")
        qs = SearchRun.objects.prefetch_related("candidates__source_documents").all()
        if category and category != "all":
            qs = qs.filter(candidates__industry=category).distinct()
        qs = qs.order_by("-created_at")[:20]
        return Response(SearchRunSerializer(qs, many=True).data)


class SearchDetailView(APIView):
    def get(self, request, run_id):
        run = SearchRun.objects.prefetch_related("candidates__source_documents").filter(pk=run_id).first()
        if run is None:
            return Response({"detail": "Запуск поиска не найден."}, status=status.HTTP_404_NOT_FOUND)
        return Response(SearchRunSerializer(run).data)
