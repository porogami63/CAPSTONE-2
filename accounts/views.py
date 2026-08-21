from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from django.contrib.auth.decorators import login_required
from accounts.decorators import role_required
from accounts.forms import UserEditForm, UserLoginForm, UserProfileForm, UserSignupForm
from accounts.models import User


def permission_denied(request, exception=None):
    return render(request, "403.html", status=403)


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    next_url = request.GET.get("next") or request.POST.get("next") or "dashboard:home"
    error_message = None

    if request.method == "POST":
        form = UserLoginForm(request.POST)
        if form.is_valid():
            login_input = form.cleaned_data.get("username").strip()
            password = form.cleaned_data.get("password")

            user_obj = User.objects.filter(
                Q(username__iexact=login_input) | Q(email__iexact=login_input)
            ).first()

            username_to_auth = user_obj.username if user_obj else login_input
            user = authenticate(request, username=username_to_auth, password=password)

            if user is not None:
                if not user.is_active:
                    error_message = "Your user account is currently disabled. Please contact system management."
                else:
                    login(request, user)
                    messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
                    return redirect(next_url)
            else:
                if user_obj and not user_obj.is_active:
                    error_message = "Your user account is currently disabled. Please contact your Administrator."
                else:
                    error_message = "Invalid username/email or password. Please check your credentials and try again."
        else:
            error_message = "Please fill in both username/email and password fields."
    else:
        form = UserLoginForm()

    return render(request, "accounts/login.html", {
        "form": form,
        "next": next_url,
        "login_error": error_message,
    })


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    if request.method == "POST":
        form = UserSignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome to HTC Core, {user.first_name or user.username}! Account created as {user.get_role_display()}.")
            return redirect("dashboard:home")
        else:
            messages.error(request, "Please correct the registration errors below.")
    else:
        form = UserSignupForm()

    return render(request, "accounts/signup.html", {"form": form})


@role_required(User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT)
def user_list_view(request):
    users = User.objects.all().order_by("-date_joined")
    return render(request, "accounts/user_list.html", {"users": users})


@role_required(User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT)
def user_edit_view(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = UserEditForm(request.POST, instance=target_user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated user profile and role for {target_user.username}.")
            return redirect("accounts:user_list")
        else:
            messages.error(request, "Error updating user profile.")
    else:
        form = UserEditForm(instance=target_user)

    return render(request, "accounts/user_edit.html", {"form": form, "target_user": target_user})


@login_required
def profile_view(request):
    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile picture and personal details have been updated successfully.")
            return redirect("accounts:profile")
        else:
            messages.error(request, "Error updating profile details.")
    else:
        form = UserProfileForm(instance=request.user)

    return render(request, "accounts/profile.html", {"form": form})

