from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("signup/", views.signup_view, name="signup"),
    path("users/", views.user_list_view, name="user_list"),
    path("users/<int:pk>/edit/", views.user_edit_view, name="user_edit"),
    path("profile/", views.profile_view, name="profile"),
]
