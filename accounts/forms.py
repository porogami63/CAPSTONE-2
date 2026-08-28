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
        widget=forms.EmailInput(attrs={"class": "form-control-htc", "placeholder": "name@heindrich.ph"}),
    )
    first_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "First Name"}),
    )
    last_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "Last Name"}),
    )
    role = forms.ChoiceField(
        choices=User.Role.choices,
        required=True,
        initial=User.Role.OPERATIONS_MANAGEMENT,
        widget=forms.Select(attrs={"class": "form-select-htc"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name", "role")
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "Choose username"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update({"class": "form-control-htc", "placeholder": "Create password"})
        self.fields["password2"].widget.attrs.update({"class": "form-control-htc", "placeholder": "Confirm password"})


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "role", "is_active", "is_staff"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control-htc"}),
            "last_name": forms.TextInput(attrs={"class": "form-control-htc"}),
            "email": forms.EmailInput(attrs={"class": "form-control-htc"}),
            "role": forms.Select(attrs={"class": "form-select-htc"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_staff": forms.CheckboxInput(attrs={"class": "form-check-input"}),
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

