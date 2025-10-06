from django.urls import path

from .views import (
    ChatConsentView,
    ChatHistoryView,
    ChatPingView,
    ChatSendView,
    ChatStartView,
    ChatStreamView,
)

app_name = "chatbot"

urlpatterns = [
    path("ping/", ChatPingView.as_view(), name="ping"),
    path("consent/", ChatConsentView.as_view(), name="consent"),
    path("start/", ChatStartView.as_view(), name="start"),
    path("send/", ChatSendView.as_view(), name="send"),
    path("history/", ChatHistoryView.as_view(), name="history"),
    path("stream/", ChatStreamView.as_view(), name="stream"),
]
