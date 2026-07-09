# Figma wireframe → Django implementation

Wireframe source: [Create Login Screen (Figma Make)](https://www.figma.com/make/fpZJzZgpJGhACxGcVbfxNC/Create-Login-Screen?p=f&t=YCWsgQLWOGf7UQwa-0&preview-route=%2Fdashboard)

Preview routes in the link map to app routes:

| Figma preview route | Django URL | Template |
|---------------------|------------|----------|
| Login screen | `/accounts/login/` | `templates/accounts/login.html` |
| `/dashboard` | `/` | `templates/dashboard/home.html` |

## Workflow for UI/UX (Bernardino)

### 1. Extract design tokens from Figma

In Figma **Dev Mode** or **Inspect**:

- Primary / accent colors → paste into `static/css/htc-theme.css` `:root` variables
- Font family and sizes → `--htc-font` and Bootstrap overrides
- Border radius, shadows → `--htc-radius`, `--htc-shadow`
- Spacing for cards and sidebar width

### 2. Export assets (if any)

- Logo → `static/img/htc-logo.svg`
- Icons → Bootstrap Icons (already used) or exported SVGs

### 3. Match layout shells

The repo uses two layout shells aligned with typical login + dashboard wireframes:

- **Login** — standalone page, no sidebar (`login.html` + `login-page` CSS)
- **App** — sidebar + main content (`app_base.html` + `app-shell` CSS)

Other screens extend `app_base.html`:

```django
{% extends "app_base.html" %}
```

### 4. Page-by-page checklist

| Screen | Status | Notes |
|--------|--------|-------|
| Login | Scaffolded | Adjust gradient, card width, button style from Figma |
| Dashboard | Scaffolded | Status cards + alert lists match wireframe sections |
| Transactions list | Uses `base.html` | Migrate to `app_base.html` for consistent sidebar |
| Transaction detail | Uses `base.html` | Same |
| Loans / Audit / Masters | Uses `base.html` | Same |

### 5. Do not rebuild in React

The capstone chose **Bootstrap 5 + Django templates**. Implement Figma visually in HTML/CSS — no need to export Figma to React unless the team changes stack.

### 6. Review loop

1. Bernardino updates Figma tokens in `htc-theme.css`
2. Cahindi/Santos verify pages in browser
3. Screenshot side-by-side with Figma for defense slides (Chapter 4)

## Quick local preview (no Docker)

```powershell
.\.venv\Scripts\python manage.py runserver
```

Login: http://127.0.0.1:8000/accounts/login/  
Dashboard: http://127.0.0.1:8000/

## CSS single source of truth

All brand styling should live in:

```
static/css/htc-theme.css
```

After CSS changes locally:

```powershell
.\.venv\Scripts\python manage.py collectstatic --noinput
```

In Docker, `collectstatic` runs automatically on container start.
