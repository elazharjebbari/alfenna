from django.urls import path

from .views import CheckoutSessionView

app_name = "checkout"

urlpatterns = [
    path("sessions/", CheckoutSessionView.as_view(), name="checkout-sessions"),
]
