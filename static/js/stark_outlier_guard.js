/**
 * Stark Outlier Guard & Confirmation Modal
 * Intercepts numerical form submissions to verify input sanity against historical Mean, Median, and Mode computations.
 * Adheres strictly to design constraints:
 * - Very prominent modal box
 * - NO emojis or icons
 * - Stark Red action button (.btn-stark-red)
 */

document.addEventListener("DOMContentLoaded", function () {
    const forms = document.querySelectorAll('form[data-outlier-guard="true"]');
    forms.forEach(form => {
        form.addEventListener("submit", function (e) {
            // If already confirmed by user, allow submission
            let confirmedField = form.querySelector('input[name="confirmed_outlier"]');
            if (confirmedField && confirmedField.value === "true") {
                return true;
            }

            e.preventDefault();

            const formData = new FormData(form);
            const csrfToken = form.querySelector('input[name="csrfmiddlewaretoken"]')?.value || getCsrfTokenCookie();

            fetch("/operations/api/stats-check/", {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrfToken,
                },
                body: formData,
            })
                .then(response => response.json())
                .then(data => {
                    if (data.is_flagged && data.outliers && data.outliers.length > 0) {
                        showStarkOutlierModal(form, data.outliers);
                    } else {
                        // Submit form normally
                        ensureConfirmedHiddenField(form, "true");
                        form.submit();
                    }
                })
                .catch(err => {
                    console.error("Outlier stats check error:", err);
                    // Fallback to regular submit on error
                    form.submit();
                });
        });
    });
});

function ensureConfirmedHiddenField(form, val) {
    let confirmedField = form.querySelector('input[name="confirmed_outlier"]');
    if (!confirmedField) {
        confirmedField = document.createElement("input");
        confirmedField.type = "hidden";
        confirmedField.name = "confirmed_outlier";
        form.appendChild(confirmedField);
    }
    confirmedField.value = val;
}

function showStarkOutlierModal(form, outliers) {
    let modalEl = document.getElementById("starkOutlierModal");
    if (!modalEl) {
        modalEl = document.createElement("div");
        modalEl.id = "starkOutlierModal";
        modalEl.className = "modal fade";
        modalEl.setAttribute("tabindex", "-1");
        modalEl.setAttribute("aria-hidden", "true");
        modalEl.setAttribute("data-bs-backdrop", "static");
        document.body.appendChild(modalEl);
    }

    let rowsHtml = outliers.map(item => `
        <tr>
            <td style="font-weight: 700;">${escapeHtml(item.label)}</td>
            <td style="font-weight: 800; color: #dc2626;">${escapeHtml(item.value.toString())}</td>
            <td>${escapeHtml(item.mean.toString())}</td>
            <td>${escapeHtml(item.median.toString())}</td>
            <td>${escapeHtml(item.mode.toString())}</td>
        </tr>
    `).join("");

    modalEl.innerHTML = `
        <div class="modal-dialog modal-dialog-centered modal-lg">
            <div class="modal-content stark-outlier-card">
                <div class="modal-header stark-outlier-header">
                    <h4 class="modal-title stark-outlier-title">Are you sure?</h4>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body p-4">
                    <p style="font-size: 1.05rem; font-weight: 600; color: var(--htc-text); margin-bottom: 1rem;">
                        One or more entered numerical values exceed historical operational thresholds.
                    </p>
                    <p style="font-size: 0.9rem; color: var(--htc-text-muted); margin-bottom: 1.25rem;">
                        Statistical calculations (Mean, Median, Mode) indicate that the values below are unusually high. 
                        Please review to ensure user input errors do not corrupt operational records.
                    </p>
                    <div class="table-responsive mb-3">
                        <table class="stark-stats-table">
                            <thead>
                                <tr>
                                    <th>Field Parameter</th>
                                    <th>Entered Value</th>
                                    <th>Historical Mean</th>
                                    <th>Historical Median</th>
                                    <th>Historical Mode</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${rowsHtml}
                            </tbody>
                        </table>
                    </div>
                    <p style="font-size: 0.85rem; color: var(--htc-text-muted); margin-bottom: 0;">
                        Clicking <strong>Confirm &amp; Proceed</strong> will record this transaction despite the statistical deviation.
                    </p>
                </div>
                <div class="modal-footer border-top p-3 d-flex justify-content-between">
                    <button type="button" class="btn btn-outline-secondary px-4 fw-bold" data-bs-dismiss="modal">
                        Cancel &amp; Revise Input
                    </button>
                    <button type="button" id="starkConfirmProceedBtn" class="btn-stark-red">
                        Confirm &amp; Proceed
                    </button>
                </div>
            </div>
        </div>
    `;

    const bsModal = new bootstrap.Modal(modalEl);
    bsModal.show();

    document.getElementById("starkConfirmProceedBtn").addEventListener("click", function () {
        bsModal.hide();
        ensureConfirmedHiddenField(form, "true");
        form.submit();
    });
}

function escapeHtml(str) {
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function getCsrfTokenCookie() {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, 10) === "csrftoken=") {
                cookieValue = decodeURIComponent(cookie.substring(10));
                break;
            }
        }
    }
    return cookieValue;
}
