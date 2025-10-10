from django.urls import path

from apps.flowforms.tests.test_stepper_e2e import StepperRealPageE2ETest
from apps.leads.views.views import LeadCollectAPIView, SignPayloadView
from apps.leads.views.views_progress import LeadProgressAPIView, EchoHeadersAPIView

app_name = "leads"
urlpatterns = [
    path("collect/", LeadCollectAPIView.as_view(), name="collect"),
    path("sign/", SignPayloadView.as_view(), name="sign"),  # ⬅️ nouveau
    path("progress/", LeadProgressAPIView.as_view(), name="progress"),
    path("debug/echo-headers/", EchoHeadersAPIView.as_view(), name="echo-headers"),
] + [
]
