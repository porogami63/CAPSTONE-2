from django import template

from accounts.permissions import user_has_perm

register = template.Library()


@register.filter
def has_perm(user, perm_name):
    return user_has_perm(user, perm_name)


@register.simple_tag
def can(user, perm_name):
    return user_has_perm(user, perm_name)
