from django import template
from operations.services.stats_services import get_operational_stats

register = template.Library()


@register.simple_tag
def get_stats_summary():
    """Returns the operational stats dictionary containing mean, median, mode for key fields."""
    return get_operational_stats()


@register.simple_tag
def field_stat(stat_dict, stat_key, metric_name):
    """
    Retrieves a specific metric ('mean', 'median', 'mode', 'std_dev') for a given field key.
    Usage: {% field_stat stats "po_volume" "mean" %}
    """
    if not stat_dict or stat_key not in stat_dict:
        return "0.0"
    return stat_dict[stat_key].get(metric_name, "0.0")
