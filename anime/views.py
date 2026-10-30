from rest_framework.generics import ListAPIView, RetrieveAPIView
from .models import AnimeEpisode
from .serializers import AnimeEpisodeSerializer

class AnimeEpisodeListView(ListAPIView):
    queryset = AnimeEpisode.objects.filter(is_published=True)
    serializer_class = AnimeEpisodeSerializer

class AnimeEpisodeDetailView(RetrieveAPIView):
    queryset = AnimeEpisode.objects.filter(is_published=True)
    serializer_class = AnimeEpisodeSerializer