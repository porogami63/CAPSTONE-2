"""Content-Security-Policy middleware.

The templates still rely on inline <script>/style blocks, so 'unsafe-inline' is retained for those
two directives. The policy nevertheless blocks: scripts/styles/fonts from unlisted origins,
data exfiltration to third-party hosts (connect-src / form-action), plugins (object-src),
base-tag hijacking and framing by other sites.

Controlled by settings: CSP_ENABLED (default on) and CSP_REPORT_ONLY (default off).
"""

from django.conf import settings

CDN_JSDELIVR = "https://cdn.jsdelivr.net"
CDN_CDNJS = "https://cdnjs.cloudflare.com"
FONTS_CSS = "https://fonts.googleapis.com"
FONTS_FILES = "https://fonts.gstatic.com"

DEFAULT_POLICY = "; ".join(
    [
        "default-src 'self'",
        f"script-src 'self' 'unsafe-inline' {CDN_JSDELIVR} {CDN_CDNJS}",
        f"style-src 'self' 'unsafe-inline' {CDN_JSDELIVR} {CDN_CDNJS} {FONTS_CSS}",
        f"font-src 'self' data: {CDN_JSDELIVR} {CDN_CDNJS} {FONTS_FILES}",
        "img-src 'self' data: blob:",
        "connect-src 'self'",
        "frame-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'self'",
    ]
)


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = getattr(settings, "CSP_ENABLED", True)
        self.report_only = getattr(settings, "CSP_REPORT_ONLY", False)
        self.policy = getattr(settings, "CSP_POLICY", DEFAULT_POLICY)

    def __call__(self, request):
        response = self.get_response(request)
        if self.enabled and "Content-Security-Policy" not in response and "Content-Security-Policy-Report-Only" not in response:
            header = "Content-Security-Policy-Report-Only" if self.report_only else "Content-Security-Policy"
            response[header] = self.policy
        return response
