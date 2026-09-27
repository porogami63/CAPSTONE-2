import base64
import hashlib
import io
import pyotp
import qrcode
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from accounts.forms import (
    AdminPasswordResetForm,
    TwoFactorVerifyForm,
    UserEditForm,
    UserLoginForm,
    UserProfileForm,
    UserSignupForm,
)
from accounts.models import User


def get_client_device_hash(request):
    ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", "127.0.0.1")
    ua = request.META.get("HTTP_USER_AGENT", "unknown")
    raw = f"{ip}:{ua}"
    return hashlib.sha256(raw.encode()).hexdigest()


def is_2fa_remembered_today(request, user):
    cookie_val = request.COOKIES.get(f"htc_2fa_remember_{user.id}")
    if not cookie_val:
        return False
    signer = TimestampSigner()
    try:
        unsigned_val = signer.unsign(cookie_val, max_age=86400)
        parts = unsigned_val.split(":")
        if len(parts) == 3:
            uid, dev_hash, date_str = parts
            current_dev_hash = get_client_device_hash(request)
            today_str = timezone.localdate().isoformat()
            if uid == str(user.id) and dev_hash == current_dev_hash and date_str == today_str:
                return True
    except (BadSignature, SignatureExpired):
        pass
    return False


def set_2fa_remember_cookie(response, request, user):
    signer = TimestampSigner()
    today_str = timezone.localdate().isoformat()
    dev_hash = get_client_device_hash(request)
    cookie_data = f"{user.id}:{dev_hash}:{today_str}"
    signed_val = signer.sign(cookie_data)
    response.set_cookie(f"htc_2fa_remember_{user.id}", signed_val, max_age=86400, httponly=True, samesite="Lax")
    return response


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
                    error_message = "Your user account is pending Administrator approval. Please contact system management."
                elif user.is_2fa_enabled:
                    if is_2fa_remembered_today(request, user):
                        login(request, user)
                        messages.success(request, f"Welcome back, {user.get_full_name() or user.username}! (2FA active for this device today)")
                        return redirect(next_url)
                    else:
                        # Stash pre-2FA state in session
                        request.session["pre_2fa_user_id"] = user.id
                        request.session["pre_2fa_next"] = next_url
                        return redirect("accounts:two_factor_verify")
                else:
                    login(request, user)
                    messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
                    return redirect(next_url)
            else:
                if user_obj and not user_obj.is_active:
                    error_message = "Your user account is pending Administrator approval. Please contact system management."
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


def two_factor_verify_view(request):
    user_id = request.session.get("pre_2fa_user_id")
    if not user_id:
        return redirect("accounts:login")

    user = get_object_or_404(User, pk=user_id)
    next_url = request.session.get("pre_2fa_next", "dashboard:home")
    error_message = None

    if request.method == "POST":
        form = TwoFactorVerifyForm(request.POST)
        if form.is_valid():
            token = form.cleaned_data.get("otp_token").strip().replace(" ", "")
            totp = pyotp.TOTP(user.otp_secret or "")
            
            # Check TOTP token or backup codes
            is_valid_totp = user.otp_secret and totp.verify(token, valid_window=1)
            is_backup_code = False
            
            if not is_valid_totp and user.backup_codes:
                if token in user.backup_codes:
                    is_backup_code = True
                    user.backup_codes.remove(token)
                    user.save(update_fields=["backup_codes"])

            if is_valid_totp or is_backup_code:
                # Clear pre-2FA session variables
                del request.session["pre_2fa_user_id"]
                if "pre_2fa_next" in request.session:
                    del request.session["pre_2fa_next"]

                login(request, user)
                messages.success(request, f"Welcome back, {user.get_full_name() or user.username}! 2FA verified for today.")
                response = redirect(next_url)
                return set_2fa_remember_cookie(response, request, user)
            else:
                error_message = "Invalid 2FA code or backup code. Please try again."
    else:
        form = TwoFactorVerifyForm()

    return render(request, "accounts/two_factor_verify.html", {
        "form": form,
        "target_user": user,
        "error_message": error_message,
    })


@login_required
def two_factor_setup_view(request):
    user = request.user
    if user.is_2fa_enabled:
        messages.info(request, "Two-Factor Authentication is already enabled on your account.")
        return redirect("accounts:profile")

    secret = request.session.get("setup_otp_secret")
    if not secret:
        secret = pyotp.random_base32()
        request.session["setup_otp_secret"] = secret

    totp = pyotp.TOTP(secret)
    qr_uri = totp.provisioning_uri(name=user.email or user.username, issuer_name="HTC Core")

    # Generate QR Code SVG / PNG in base64
    qr_img = qrcode.make(qr_uri)
    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_code_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    error_message = None

    if request.method == "POST":
        token = request.POST.get("otp_token", "").strip().replace(" ", "")
        if totp.verify(token, valid_window=1):
            # Generate 5 backup codes
            backup_codes = [secrets.token_hex(4).upper() for _ in range(5)]
            
            user.otp_secret = secret
            user.is_2fa_enabled = True
            user.backup_codes = backup_codes
            user.save()

            if "setup_otp_secret" in request.session:
                del request.session["setup_otp_secret"]

            messages.success(request, "Two-Factor Authentication has been enabled successfully!")
            return render(request, "accounts/two_factor_success.html", {
                "backup_codes": backup_codes,
            })
        else:
            error_message = "Invalid verification code. Please make sure your authenticator app is synced."

    return render(request, "accounts/two_factor_setup.html", {
        "secret": secret,
        "qr_code_b64": qr_code_b64,
        "error_message": error_message,
    })


@login_required
def two_factor_disable_view(request):
    if request.method == "POST":
        user = request.user
        user.is_2fa_enabled = False
        user.otp_secret = None
        user.backup_codes = []
        user.save()
        messages.success(request, "Two-Factor Authentication has been disabled for your account.")
    return redirect("accounts:profile")


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    if request.method == "POST":
        form = UserSignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.role = User.Role.OPERATIONS_MANAGEMENT
            user.save()
            messages.success(
                request,
                f"Registration request submitted for {user.get_full_name() or user.username}! Your account is pending Administrator approval before you can sign in."
            )
            return redirect("accounts:login")
        else:
            messages.error(request, "Please correct the registration errors below.")
    else:
        form = UserSignupForm()

    return render(request, "accounts/signup.html", {"form": form})


@role_required(User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT)
def user_list_view(request):
    users = User.objects.all().order_by("-date_joined")
    pending_users = users.filter(is_active=False)
    active_users = users.filter(is_active=True)
    return render(request, "accounts/user_list.html", {
        "users": users,
        "pending_users": pending_users,
        "active_users": active_users,
        "roles": User.Role.choices,
    })


@role_required(User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT)
def user_approve_view(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        target_user.is_active = True
        role = request.POST.get("role")
        if role and role in dict(User.Role.choices):
            target_user.role = role
        target_user.save()
        messages.success(request, f"Approved user account {target_user.username} as {target_user.get_role_display()}.")
    return redirect("accounts:user_list")


@role_required(User.Role.ADMINISTRATOR, User.Role.OPERATIONS_MANAGEMENT)
def user_reset_password_view(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = AdminPasswordResetForm(request.POST)
        if form.is_valid():
            new_pass = form.cleaned_data.get("new_password")
            target_user.set_password(new_pass)
            target_user.save()
            messages.success(request, f"Password for {target_user.username} has been reset successfully.")
            return redirect("accounts:user_list")
        else:
            messages.error(request, "Error resetting password. Please check the inputs.")
    else:
        form = AdminPasswordResetForm()

    return render(request, "accounts/admin_reset_password.html", {
        "form": form,
        "target_user": target_user,
    })


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

