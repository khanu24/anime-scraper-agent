from django.contrib import admin
from .models import AnimeEpisode

@admin.register(AnimeEpisode)
class AnimeEpisodeAdmin(admin.ModelAdmin):
    list_display = ('title', 'source_url', 'is_published', 'created_at')
    search_fields = ('title', 'source_url')
    list_filter = ('is_published', 'created_at')