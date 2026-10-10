/**
 * HTC Core - Website-wide Form Draft Caching & Auto-Restore
 * 
 * Automatically caches in-progress form inputs in localStorage when navigating away,
 * swapping pages, or refreshing, and seamlessly restores them upon return.
 * 
 * Security & Privacy constraints:
 * - NEVER caches passwords or sensitive authentication/login credentials
 * - NEVER caches login email/username fields on authentication forms
 * - NEVER caches CSRF tokens, OTPs, or 2FA codes
 * - Clears cached draft upon successful form submission or form reset
 * - Automatically purges expired drafts (> 48 hours old)
 */

(function () {
    const STORAGE_PREFIX = "htc_form_draft_v1:";
    const DRAFT_MAX_AGE_MS = 48 * 60 * 60 * 1000; // 48 hours

    // Fields that must NEVER be cached under any circumstances
    const SENSITIVE_FIELD_NAMES = new Set([
        "password",
        "old_password",
        "new_password",
        "password1",
        "password2",
        "confirm_password",
        "csrfmiddlewaretoken",
        "otp",
        "token",
        "totp",
        "two_factor",
        "verification_code",
        "auth_code"
    ]);

    /**
     * Determines whether a form is a login / authentication form.
     */
    function isAuthForm(form) {
        if (!form) return false;
        const action = (form.getAttribute("action") || "").toLowerCase();
        const formId = (form.id || "").toLowerCase();
        const formName = (form.getAttribute("name") || "").toLowerCase();
        const currentPath = window.location.pathname.toLowerCase();

        // Check if page path is an auth page
        if (currentPath.includes("/accounts/login") ||
            currentPath.includes("/accounts/two-factor") ||
            currentPath.includes("/accounts/logout")) {
            return true;
        }

        // Check if form action points to auth
        if (action.includes("/accounts/login") ||
            action.includes("/accounts/two-factor") ||
            action.includes("/accounts/logout")) {
            return true;
        }

        // Check if form has password fields
        if (form.querySelector('input[type="password"]')) {
            return true;
        }

        if (formId.includes("login") || formName.includes("login")) {
            return true;
        }

        return false;
    }

    /**
     * Determines whether an input is eligible for draft caching.
     */
    function isFieldCacheable(input, form) {
        if (!input) return false;

        const type = (input.type || "text").toLowerCase();

        // Never cache passwords, file uploads, buttons, or submit/reset triggers
        if (type === "password" || type === "file" || type === "submit" || type === "reset" || type === "button") {
            return false;
        }

        // Never cache hidden fields (e.g. CSRF tokens, internal flags)
        if (type === "hidden") {
            return false;
        }

        const name = (input.name || input.id || "").toLowerCase();
        if (!name) return false;

        // Never cache sensitive security tokens or passwords
        if (SENSITIVE_FIELD_NAMES.has(name) || /password/i.test(name)) {
            return false;
        }

        // Exclude email and username on login / auth forms
        if (isAuthForm(form)) {
            if (/^(email|username|login|user_login|identifier)$/i.test(name)) {
                return false;
            }
        }

        // Exclude explicitly opted-out fields or forms
        if (input.hasAttribute("data-no-cache") || (form && form.hasAttribute("data-no-cache"))) {
            return false;
        }

        return true;
    }

    /**
     * Generate a unique storage key for a form on the current page.
     */
    function getFormStorageKey(form, index) {
        const path = window.location.pathname;
        const formId = form.id || form.getAttribute("name") || form.getAttribute("action") || ("form_" + index);
        return STORAGE_PREFIX + path + ":" + formId;
    }

    /**
     * Read the current value of a form field.
     */
    function getFieldValue(input) {
        const type = (input.type || "").toLowerCase();
        if (type === "checkbox") {
            return input.checked;
        }
        if (type === "radio") {
            return input.checked ? input.value : null;
        }
        if (input.tagName === "SELECT" && input.multiple) {
            return Array.from(input.selectedOptions).map(opt => opt.value);
        }
        return input.value;
    }

    /**
     * Save all eligible inputs for a form into localStorage.
     */
    function saveFormDraft(form, index) {
        if (isAuthForm(form)) return;

        const storageKey = getFormStorageKey(form, index);
        const fields = {};
        let hasValues = false;

        const elements = form.querySelectorAll("input, select, textarea");
        elements.forEach(input => {
            if (!isFieldCacheable(input, form)) return;

            const name = input.name || input.id;
            if (!name) return;

            const val = getFieldValue(input);
            if (val !== null && val !== undefined) {
                // If it's a non-empty string or boolean true/false or array with elements
                if (typeof val === "boolean") {
                    fields[name] = val;
                    if (val) hasValues = true;
                } else if (Array.isArray(val)) {
                    if (val.length > 0) {
                        fields[name] = val;
                        hasValues = true;
                    }
                } else if (String(val).trim() !== "") {
                    fields[name] = val;
                    hasValues = true;
                }
            }
        });

        if (hasValues) {
            try {
                const payload = {
                    timestamp: Date.now(),
                    path: window.location.pathname,
                    fields: fields
                };
                localStorage.setItem(storageKey, JSON.stringify(payload));
            } catch (err) {
                console.warn("[HTC Draft Cache] Failed to save draft:", err);
            }
        } else {
            // If all fields are empty, clear existing key
            try {
                localStorage.removeItem(storageKey);
            } catch (e) {}
        }
    }

    /**
     * Clear the draft for a form upon submission or reset.
     */
    function clearFormDraft(form, index) {
        const storageKey = getFormStorageKey(form, index);
        try {
            localStorage.removeItem(storageKey);
        } catch (e) {}
        removeDraftNotice(form);
    }

    /**
     * Display a subtle, non-intrusive notification badge indicating inputs were restored.
     */
    function showDraftRestoredNotice(form, onClearCallback) {
        const noticeId = "htcDraftNotice_" + (form.id || "main");
        let existing = document.getElementById(noticeId);
        if (existing) existing.remove();

        const notice = document.createElement("div");
        notice.id = noticeId;
        notice.className = "htc-draft-restored-pill";
        notice.setAttribute("role", "status");
        notice.innerHTML = `
            <div class="d-flex align-items-center justify-content-between gap-2">
                <span class="d-flex align-items-center gap-1">
                    <i class="bi bi-clock-history text-primary"></i>
                    <span>In-progress draft restored from previous session.</span>
                </span>
                <button type="button" class="btn btn-link btn-sm p-0 text-decoration-none fw-bold draft-clear-btn" style="font-size: 0.75rem; color: var(--htc-text-muted);">
                    Discard Draft
                </button>
            </div>
        `;

        // Insert at the top of the form
        if (form.firstChild) {
            form.insertBefore(notice, form.firstChild);
        } else {
            form.appendChild(notice);
        }

        const clearBtn = notice.querySelector(".draft-clear-btn");
        if (clearBtn) {
            clearBtn.addEventListener("click", function () {
                if (typeof onClearCallback === "function") {
                    onClearCallback();
                }
                notice.remove();
            });
        }

        // Auto-fade notice after 7 seconds
        setTimeout(function () {
            if (notice && notice.parentNode) {
                notice.style.transition = "opacity 0.4s ease, transform 0.4s ease";
                notice.style.opacity = "0";
                notice.style.transform = "translateY(-4px)";
                setTimeout(() => notice.remove(), 400);
            }
        }, 7000);
    }

    function removeDraftNotice(form) {
        const noticeId = "htcDraftNotice_" + (form.id || "main");
        const existing = document.getElementById(noticeId);
        if (existing) existing.remove();
    }

    /**
     * Restore cached draft into form inputs.
     */
    function restoreFormDraft(form, index) {
        if (isAuthForm(form)) return;

        const storageKey = getFormStorageKey(form, index);
        let raw = null;
        try {
            raw = localStorage.getItem(storageKey);
        } catch (e) {
            return;
        }

        if (!raw) return;

        let payload = null;
        try {
            payload = JSON.parse(raw);
        } catch (e) {
            localStorage.removeItem(storageKey);
            return;
        }

        if (!payload || !payload.fields) return;

        // Expire if older than DRAFT_MAX_AGE_MS
        if (payload.timestamp && (Date.now() - payload.timestamp > DRAFT_MAX_AGE_MS)) {
            localStorage.removeItem(storageKey);
            return;
        }

        let restoredCount = 0;
        const fields = payload.fields;

        Object.keys(fields).forEach(name => {
            const savedVal = fields[name];
            // Find input by name or id within this form
            let input = form.elements[name] || form.querySelector(`[name="${name}"], #${name}`);
            if (!input) return;

            // Handle radio NodeList
            if (input instanceof RadioNodeList || (input.length && input[0] && input[0].type === "radio")) {
                const radioOption = form.querySelector(`input[name="${name}"][value="${savedVal}"]`);
                if (radioOption && !radioOption.checked) {
                    radioOption.checked = true;
                    radioOption.dispatchEvent(new Event("change", { bubbles: true }));
                    restoredCount++;
                }
                return;
            }

            if (!isFieldCacheable(input, form)) return;

            const type = (input.type || "").toLowerCase();

            if (type === "checkbox") {
                if (input.checked !== savedVal) {
                    input.checked = !!savedVal;
                    input.dispatchEvent(new Event("change", { bubbles: true }));
                    restoredCount++;
                }
            } else if (input.tagName === "SELECT") {
                if (input.multiple && Array.isArray(savedVal)) {
                    let changed = false;
                    Array.from(input.options).forEach(opt => {
                        const shouldSelect = savedVal.includes(opt.value);
                        if (opt.selected !== shouldSelect) {
                            opt.selected = shouldSelect;
                            changed = true;
                        }
                    });
                    if (changed) {
                        input.dispatchEvent(new Event("change", { bubbles: true }));
                        restoredCount++;
                    }
                } else {
                    if (input.value !== String(savedVal)) {
                        input.value = savedVal;
                        input.dispatchEvent(new Event("change", { bubbles: true }));
                        restoredCount++;
                    }
                }
            } else {
                // Text, Number, Textarea, Date, etc.
                // Restore if current value differs from saved value
                if (input.value !== String(savedVal)) {
                    input.value = savedVal;
                    input.dispatchEvent(new Event("input", { bubbles: true }));
                    input.dispatchEvent(new Event("change", { bubbles: true }));
                    restoredCount++;
                }
            }
        });

        if (restoredCount > 0) {
            showDraftRestoredNotice(form, function () {
                // Discard draft action
                clearFormDraft(form, index);
                form.reset();
            });
        }
    }

    /**
     * Debounce utility.
     */
    function debounce(func, wait) {
        let timeout;
        return function (...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }

    /**
     * Clean up any expired drafts across all pages to keep localStorage tidy.
     */
    function pruneExpiredDrafts() {
        try {
            const keysToRemove = [];
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (key && key.startsWith(STORAGE_PREFIX)) {
                    try {
                        const item = JSON.parse(localStorage.getItem(key));
                        if (item && item.timestamp && (Date.now() - item.timestamp > DRAFT_MAX_AGE_MS)) {
                            keysToRemove.push(key);
                        }
                    } catch (e) {
                        keysToRemove.push(key);
                    }
                }
            }
            keysToRemove.forEach(k => localStorage.removeItem(k));
        } catch (e) {}
    }

    /**
     * Initialize draft caching on all forms on the page.
     */
    function initDraftCache() {
        pruneExpiredDrafts();

        const forms = document.querySelectorAll("form");
        forms.forEach((form, index) => {
            if (isAuthForm(form)) return;

            // Restore in-progress inputs on load
            restoreFormDraft(form, index);

            // Debounced auto-save on user input
            const debouncedSave = debounce(() => saveFormDraft(form, index), 200);

            form.addEventListener("input", function (e) {
                if (isFieldCacheable(e.target, form)) {
                    debouncedSave();
                }
            });

            form.addEventListener("change", function (e) {
                if (isFieldCacheable(e.target, form)) {
                    saveFormDraft(form, index);
                }
            });

            // Clear draft when form is submitted
            form.addEventListener("submit", function () {
                clearFormDraft(form, index);
            });

            // Clear draft when form is reset
            form.addEventListener("reset", function () {
                clearFormDraft(form, index);
            });
        });

        // Flush save before page unload / navigation swap
        window.addEventListener("beforeunload", function () {
            forms.forEach((form, index) => {
                if (!isAuthForm(form)) {
                    saveFormDraft(form, index);
                }
            });
        });

        window.addEventListener("pagehide", function () {
            forms.forEach((form, index) => {
                if (!isAuthForm(form)) {
                    saveFormDraft(form, index);
                }
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initDraftCache);
    } else {
        initDraftCache();
    }

    // Re-check on pageshow (e.g. back/forward cache traversal)
    window.addEventListener("pageshow", function (event) {
        if (event.persisted) {
            initDraftCache();
        }
    });
})();
