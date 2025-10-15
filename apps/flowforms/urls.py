from django.urls import path

from .views import HealthCheckView
from .views.landing import LandingFormView
from .views.wizard import FlowFormsWizardView

app_name = "flowforms"

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health"),
    path("landing/", LandingFormView.as_view(), name="landing-short"),
    path("<slug:flow_key>/", FlowFormsWizardView.as_view(), name="wizard"),
]
