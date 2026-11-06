from django import template

from accounts.permissions import user_has_perm, nav_is_active

register = template.Library()

ROLE_DISPLAY_MAP = {
    "administrator": "Administrator",
    "operations_management": "Operations Manager",
    "operations": "Operations",
    "finance": "Finance",
    "invoicing": "Invoicing",
}


@register.filter
def role_display(role):
    if not role:
        return ""
    role_str = str(role).strip().lower()
    return ROLE_DISPLAY_MAP.get(role_str, str(role).replace("_", " ").title())


@register.filter
def has_perm(user, perm_name):
    return user_has_perm(user, perm_name)


@register.simple_tag
def can(user, perm_name):
    return user_has_perm(user, perm_name)


@register.simple_tag
def is_nav_active(view_name, url_name, prefixes):
    return nav_is_active(view_name, url_name, prefixes)
