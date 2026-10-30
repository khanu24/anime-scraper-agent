from rest_framework import serializers
from .models import AnimeEpisode

class AnimeEpisodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnimeEpisode
        fields = ['id', 'title', 'source_url', 'thumbnail', 'stream_urls', 'is_published', 'created_at']