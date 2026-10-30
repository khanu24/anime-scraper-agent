from django.db import models

class AnimeEpisode(models.Model):
    title = models.CharField(max_length=500)
    source_url = models.URLField(unique=True)
    thumbnail = models.URLField(blank=True, null=True)
    stream_urls = models.JSONField(default=list)  # Direct links/embed script URLs save honge
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']