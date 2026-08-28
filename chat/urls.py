from django.urls import path
from . import views

app_name = "chat"

urlpatterns = [
    path("", views.chat_room_view, name="room"),
    path("api/messages/", views.api_fetch_messages, name="api_messages"),
    path("api/send/", views.api_send_message, name="api_send"),
    path("api/unread/", views.api_unread_count, name="api_unread"),
]
