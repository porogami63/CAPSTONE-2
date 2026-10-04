from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("forgot-password/", views.forgot_password_view, name="forgot_password"),
    path("reset-password/<str:uidb64>/<str:token>/", views.password_reset_confirm_view, name="password_reset_confirm"),
    path("two-factor-verify/", views.two_factor_verify_view, name="two_factor_verify"),
    path("two-factor-setup/", views.two_factor_setup_view, name="two_factor_setup"),
    path("two-factor-disable/", views.two_factor_disable_view, name="two_factor_disable"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("signup/", views.signup_view, name="signup"),
    path("users/", views.user_list_view, name="user_list"),
    path("users/<int:pk>/edit/", views.user_edit_view, name="user_edit"),
    path("users/<int:pk>/approve/", views.user_approve_view, name="user_approve"),
    path("users/<int:pk>/reset-password/", views.user_reset_password_view, name="user_reset_password"),
    path("profile/", views.profile_view, name="profile"),
]
