from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SearchRun
from .serializers import CreateSearchSerializer, SearchRunSerializer
from .tasks import start_search


class SearchCollectionView(APIView):
    def post(self, request):
        serializer = CreateSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = SearchRun.objects.create(query=serializer.validated_data["query"])
        start_search.delay(str(run.id))
        return Response(SearchRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class SearchDetailView(APIView):
    def get(self, request, run_id):
        run = SearchRun.objects.prefetch_related("candidates__source_documents").filter(pk=run_id).first()
        if run is None:
            return Response({"detail": "Запуск поиска не найден."}, status=status.HTTP_404_NOT_FOUND)
        return Response(SearchRunSerializer(run).data)
