from django.urls import path

from .views import LeadCollectAPIView, SignPayloadView
from .views_progress import LeadProgressAPIView

app_name = "leads"
urlpatterns = [
    path("collect/", LeadCollectAPIView.as_view(), name="collect"),
    path("sign/", SignPayloadView.as_view(), name="sign"),  # ⬅️ nouveau
    path("progress/", LeadProgressAPIView.as_view(), name="progress"),
]
