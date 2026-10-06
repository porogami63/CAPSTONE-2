"""Authenticated media serving.

Uploaded documents (loan clearance advices, waybills, MRO scans, avatars) used to be served
directly by Nginx without any authentication. They are now streamed through Django so a valid
session (and, for finance documents, the right role) is required. Only an allow-list of content
types is ever rendered inline; anything else is forced to download as an opaque binary.
"""

import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET

from accounts.permissions import user_has_perm

INLINE_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# Sub-folders of MEDIA_ROOT that need a specific permission in addition to being logged in.
RESTRICTED_PREFIXES = {
    "loan_settlements/": "view_loans",
}


@require_GET
@login_required
@xframe_options_sameorigin
def protected_media(request, path):
    root = Path(settings.MEDIA_ROOT).resolve()
    try:
        target = (root / path).resolve()
    except (OSError, ValueError):
        raise Http404("Not found")

    # Block path traversal and anything that is not a regular file inside MEDIA_ROOT.
    if root not in target.parents or not target.is_file():
        raise Http404("Not found")

    rel = target.relative_to(root).as_posix()
    for prefix, perm in RESTRICTED_PREFIXES.items():
        if rel.startswith(prefix) and not user_has_perm(request.user, perm):
            raise PermissionDenied

    ext = target.suffix.lower()
    inline_type = INLINE_TYPES.get(ext)
    if inline_type:
        response = FileResponse(open(target, "rb"), content_type=inline_type)
        response["Content-Disposition"] = f'inline; filename="{target.name}"'
    else:
        guessed = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        response = FileResponse(open(target, "rb"), content_type="application/octet-stream", as_attachment=True, filename=target.name)
        response["X-Original-Content-Type"] = guessed

    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=3600"
    if ext != ".pdf":
        # Neutralise any active content that might slip through; PDFs are excluded because
        # browsers' built-in PDF viewers do not work inside a sandboxed CSP.
        response["Content-Security-Policy"] = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"
    return response
