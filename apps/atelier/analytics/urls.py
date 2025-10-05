"""URL patterns for analytics endpoints."""
from django.urls import path

from .views import CollectAPIView
from .views_read import ComponentStatsView, HeatmapBucketsView

urlpatterns = [
    path("collect/", CollectAPIView.as_view(), name="analytics-collect"),
    path("components/", ComponentStatsView.as_view(), name="analytics-components"),
    path("heatmap/", HeatmapBucketsView.as_view(), name="analytics-heatmap"),
]

__all__ = ["urlpatterns"]
