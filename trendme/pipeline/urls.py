from django.urls import path

from .views import SearchCollectionView, SearchDetailView

urlpatterns = [
    path("searches/", SearchCollectionView.as_view(), name="search-collection"),
    path("searches/<uuid:run_id>/", SearchDetailView.as_view(), name="search-detail"),
]
