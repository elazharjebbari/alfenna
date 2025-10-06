from django.urls import path
from .views import VideoStreamView, ProgressUpdateView, CommentCreateView

app_name = "learning"

urlpatterns = [
    path("stream/<int:pk>/", VideoStreamView.as_view(), name="stream"),
    path("progress/<int:pk>/", ProgressUpdateView.as_view(), name="progress"),
    path("comment/<int:pk>/", CommentCreateView.as_view(), name="comment"),
]
