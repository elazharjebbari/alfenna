# apps/content/urls.py
from django.urls import path
from .views import LectureDetailView, LectureDetailPKView

urlpatterns = [
    path(
        '<slug:course_slug>/lecons/<int:section_order>-<int:lecture_order>/',
        LectureDetailView.as_view(),
        name='lecture'
    ),
    # route “jolie” (slug + ordres)
    path(
        "<slug:course_slug>/s<int:section_order>/l<int:lecture_order>/",
        LectureDetailView.as_view(),
        name="lecture-detail",
    ),
    # fallback par PK (utile pour redirections internes/tests)
    path(
        "lecture/<int:pk>/",
        LectureDetailPKView.as_view(),
        name="lecture-detail-pk",
    ),
]