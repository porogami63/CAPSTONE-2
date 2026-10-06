from django import forms
from django.contrib.auth.forms import UserCreationForm
from accounts.models import User


class UserLoginForm(forms.Form):
    username = forms.CharField(
        label="Username or Email",
        widget=forms.TextInput(
            attrs={
                "class": "form-control-htc",
                "placeholder": "Enter username or email address",
                "autofocus": True,
                "required": True,
                "id": "id_username",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control-htc",
                "placeholder": "Enter password",
                "required": True,
                "id": "id_password",
            }
        ),
    )


class UserSignupForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control-htc", "placeholder": "name@heindrich.net"}),
    )
    first_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "First Name"}),
    )
    last_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "Last Name"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name")
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "Choose username"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update({"class": "form-control-htc", "placeholder": "Create password"})
        self.fields["password2"].widget.attrs.update({"class": "form-control-htc", "placeholder": "Confirm password"})


class AdminPasswordResetForm(forms.Form):
    new_password = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(attrs={"class": "form-control-htc", "placeholder": "Enter new password"}),
    )
    confirm_password = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(attrs={"class": "form-control-htc", "placeholder": "Confirm new password"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("new_password")
        p2 = cleaned_data.get("confirm_password")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "role", "is_active"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control-htc"}),
            "last_name": forms.TextInput(attrs={"class": "form-control-htc"}),
            "email": forms.EmailInput(attrs={"class": "form-control-htc"}),
            "role": forms.Select(attrs={"class": "form-select-htc"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "avatar"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control-htc"}),
            "last_name": forms.TextInput(attrs={"class": "form-control-htc"}),
            "email": forms.EmailInput(attrs={"class": "form-control-htc"}),
            "avatar": forms.FileInput(attrs={"class": "form-control-htc", "accept": "image/*"}),
        }


class TwoFactorVerifyForm(forms.Form):
    otp_token = forms.CharField(
        label="Authenticator Code / Backup Code",
        max_length=10,
        widget=forms.TextInput(
            attrs={
                "class": "form-control otp-token-input",
                "placeholder": "000000",
                "autocomplete": "off",
                "autofocus": True,
                "inputmode": "numeric",
                "maxlength": "10",
                "id": "id_otp_token",
            }
        ),
    )


class ForgotPasswordForm(forms.Form):
    username_or_email = forms.CharField(
        label="Username or Email Address",
        widget=forms.TextInput(
            attrs={
                "class": "form-control-htc",
                "placeholder": "Enter registered username or email",
                "autofocus": True,
                "required": True,
                "id": "id_username_or_email",
            }
        ),
    )


class PasswordResetConfirmForm(forms.Form):
    new_password = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control-htc",
                "placeholder": "Enter new password (min. 8 characters)",
                "required": True,
                "id": "id_new_password",
            }
        ),
    )
    confirm_password = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control-htc",
                "placeholder": "Re-enter new password",
                "required": True,
                "id": "id_confirm_password",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("new_password")
        p2 = cleaned_data.get("confirm_password")

        if p1 and len(p1) < 8:
            self.add_error("new_password", "Password must be at least 8 characters long.")
        if p1 and p2 and p1 != p2:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned_data


