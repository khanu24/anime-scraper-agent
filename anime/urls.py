from django.urls import path
from .views import AnimeEpisodeListView, AnimeEpisodeDetailView

urlpatterns = [
    path('episodes/', AnimeEpisodeListView.as_warn if hasattr(AnimeEpisodeListView, 'as_warn') else AnimeEpisodeListView.as_view(), name='episode-list'),
    path('episodes/<int:pk>/', AnimeEpisodeDetailView.as_view(), name='episode-detail'),
]