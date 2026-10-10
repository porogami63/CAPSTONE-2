/**
 * Real-time Outlier Guard & Live Input Notice/Tooltip
 * Replaces the intrusive submission modal with instantaneous, inline notices & tooltips
 * directly attached to input boxes as values are entered.
 *
 * Automatically monitors numerical fields against historical Mean, Median, and Mode thresholds:
 * - Purchase Order Volume (MT)
 * - Supplier Sourcing Price (₱/MT)
 * - Customer Selling Price (₱/MT)
 * - Brix Quality Level (%)
 * - CHAI Quality Rating Grade
 * - Molasses Release Tons & Logistics Volume
 */

(function () {
    const FIELD_PARAM_MAP = {
        volume_mt: "po_volume",
        unit_price: "po_unit_price",
        selling_price: "po_selling_price",
        brix_level: "po_brix",
        chai_specs: "chai_grade",
        chai_value: "chai_grade",
        chai_brix: "chai_brix",
        tons: "mro_tons",
        loaded_volume_mt: "logistics_loaded",
        amount: "invoice_amount",
    };

    let cachedOperationalStats = null;
    let statsFetchPromise = null;

    /**
     * Fetch operational stats once and cache in memory for 0ms client-side validation.
     */
    function getOperationalStats() {
        if (cachedOperationalStats) {
            return Promise.resolve(cachedOperationalStats);
        }
        if (statsFetchPromise) {
            return statsFetchPromise;
        }

        statsFetchPromise = fetch("/operations/api/stats-check/?get_thresholds=true")
            .then(res => res.json())
            .then(data => {
                cachedOperationalStats = data.operational_stats || {};
                return cachedOperationalStats;
            })
            .catch(err => {
                console.warn("Could not prefetch operational statistics:", err);
                cachedOperationalStats = {};
                return cachedOperationalStats;
            });

        return statsFetchPromise;
    }

    /**
     * Format numbers into readable strings with appropriate units/currency.
     */
    function formatStatValue(num, fieldKey) {
        if (num === null || num === undefined || isNaN(num)) return "0.00";
        const val = Number(num);
        const formatted = val.toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });

        if (fieldKey === "unit_price" || fieldKey === "selling_price" || fieldKey === "amount") {
            return "₱" + formatted;
        }
        if (fieldKey === "volume_mt" || fieldKey === "tons" || fieldKey === "loaded_volume_mt") {
            return formatted + " MT";
        }
        if (fieldKey === "brix_level" || fieldKey === "chai_brix") {
            return formatted + "%";
        }
        return formatted;
    }

    /**
     * Escape HTML strings for safety.
     */
    function escapeHtml(str) {
        return String(str || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    /**
     * Extract numerical value from input text.
     */
    function parseNumericValue(valStr) {
        if (!valStr || valStr.trim() === "") return null;
        const clean = String(valStr).replace(/,/g, "").trim();
        const num = parseFloat(clean);
        return isNaN(num) ? null : num;
    }

    /**
     * Remove outlier notice and warning styling from an input.
     */
    function clearInputNotice(input) {
        input.classList.remove("is-outlier-warning");
        const addonGroup = input.closest(".input-addon-group");
        if (addonGroup) {
            addonGroup.classList.remove("has-outlier-warning");
        }

        const noticeId = "outlierNotice_" + (input.name || input.id);
        const existingNotice = document.getElementById(noticeId);
        if (existingNotice) {
            const tooltipTrigger = existingNotice.querySelector('[data-bs-toggle="tooltip"]');
            if (tooltipTrigger && window.bootstrap && bootstrap.Tooltip) {
                const inst = bootstrap.Tooltip.getInstance(tooltipTrigger);
                if (inst) inst.dispose();
            }
            existingNotice.remove();
        }
    }

    /**
     * Render or update live inline notice and tooltip for an input.
     */
    function renderInputNotice(input, fieldKey, statInfo, enteredVal) {
        input.classList.add("is-outlier-warning");
        const addonGroup = input.closest(".input-addon-group");
        if (addonGroup) {
            addonGroup.classList.add("has-outlier-warning");
        }

        const noticeId = "outlierNotice_" + (input.name || input.id);
        let noticeEl = document.getElementById(noticeId);

        const enteredFormatted = formatStatValue(enteredVal, fieldKey);
        const meanFormatted = formatStatValue(statInfo.mean, fieldKey);
        const medianFormatted = formatStatValue(statInfo.median, fieldKey);
        const modeFormatted = formatStatValue(statInfo.mode, fieldKey);
        const thresholdFormatted = formatStatValue(statInfo.high_threshold, fieldKey);

        const tooltipHtml = `<strong>Statistical calculations (Mean, Median, Mode) indicate this value is unusually high:</strong><br><br>` +
            `• <strong>Field:</strong> ${escapeHtml(statInfo.label)}<br>` +
            `• <strong>Entered Value:</strong> ${escapeHtml(enteredFormatted)}<br>` +
            `• <strong>Historical Mean:</strong> ${escapeHtml(meanFormatted)}<br>` +
            `• <strong>Historical Median:</strong> ${escapeHtml(medianFormatted)}<br>` +
            `• <strong>Historical Mode:</strong> ${escapeHtml(modeFormatted)}<br>` +
            `• <strong>Historical Threshold:</strong> ${escapeHtml(thresholdFormatted)}<br><br>` +
            `<small style="opacity:0.9;">Please review input to ensure numerical typos do not corrupt records.</small>`;

        const innerHtml = `
            <div class="outlier-notice-pill">
                <div class="outlier-body">
                    <span class="outlier-badge-tag">
                        <i class="bi bi-exclamation-triangle-fill text-warning"></i>
                        <span>Unusually High Value:</span>
                    </span>
                    <span class="outlier-stats-text">
                        Historical Mean: <strong>${escapeHtml(meanFormatted)}</strong> | Median: <strong>${escapeHtml(medianFormatted)}</strong> | Mode: <strong>${escapeHtml(modeFormatted)}</strong>
                    </span>
                </div>
                <button type="button" class="outlier-info-btn" data-bs-toggle="tooltip" data-bs-placement="top" data-bs-html="true" data-bs-title="${escapeHtml(tooltipHtml)}" title="${escapeHtml(tooltipHtml)}" aria-label="Detailed Statistical Outlier Breakdown">
                    <i class="bi bi-info-circle-fill"></i>
                </button>
            </div>
        `;

        if (!noticeEl) {
            noticeEl = document.createElement("div");
            noticeEl.id = noticeId;
            noticeEl.className = "outlier-field-notice";
            noticeEl.setAttribute("role", "alert");

            // Insert directly below input or addon group (before helper text or errors)
            const targetContainer = addonGroup || input;
            if (targetContainer.nextSibling) {
                targetContainer.parentNode.insertBefore(noticeEl, targetContainer.nextSibling);
            } else {
                targetContainer.parentNode.appendChild(noticeEl);
            }
        }

        noticeEl.innerHTML = innerHtml;

        // Initialize Bootstrap Tooltip on info button
        const tooltipTrigger = noticeEl.querySelector('[data-bs-toggle="tooltip"]');
        if (tooltipTrigger && window.bootstrap && bootstrap.Tooltip) {
            const oldInst = bootstrap.Tooltip.getInstance(tooltipTrigger);
            if (oldInst) oldInst.dispose();
            new bootstrap.Tooltip(tooltipTrigger);
        }
    }

    /**
     * Evaluate single input against statistical thresholds.
     */
    function evaluateInput(input, operationalStats) {
        const fieldKey = input.name || input.id;
        const statKey = FIELD_PARAM_MAP[fieldKey];
        if (!statKey || !operationalStats || !operationalStats[statKey]) {
            clearInputNotice(input);
            return;
        }

        const statInfo = operationalStats[statKey];
        const enteredVal = parseNumericValue(input.value);

        if (enteredVal === null) {
            clearInputNotice(input);
            return;
        }

        // Statistical threshold check: must have prior records and exceed high threshold
        if (statInfo.count >= 2 && statInfo.high_threshold > 0 && enteredVal > statInfo.high_threshold) {
            renderInputNotice(input, fieldKey, statInfo, enteredVal);
        } else {
            clearInputNotice(input);
        }
    }

    /**
     * Ensure confirmed_outlier hidden input exists on form so backend can accept submitted transaction.
     */
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

    /**
     * Debounce helper for smooth keystroke input handling.
     */
    function debounce(func, wait) {
        let timeout;
        return function (...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }

    /**
     * Initialize outlier guard on all configured forms.
     */
    function initOutlierGuard() {
        const forms = document.querySelectorAll('form[data-outlier-guard="true"]');
        if (!forms.length) return;

        getOperationalStats().then(stats => {
            forms.forEach(form => {
                // Ensure form can submit without modal blockage
                ensureConfirmedHiddenField(form, "true");

                // Find all monitored inputs in this form
                Object.keys(FIELD_PARAM_MAP).forEach(fieldName => {
                    const selector = `input[name="${fieldName}"], input#id_${fieldName}`;
                    const inputs = form.querySelectorAll(selector);

                    inputs.forEach(input => {
                        const debouncedEval = debounce(() => evaluateInput(input, stats), 180);

                        input.addEventListener("input", debouncedEval);
                        input.addEventListener("change", () => evaluateInput(input, stats));
                        input.addEventListener("blur", () => evaluateInput(input, stats));

                        // Initial check for pre-filled / edit forms
                        if (input.value && input.value.trim() !== "") {
                            evaluateInput(input, stats);
                        }
                    });
                });

                // Smooth submission without modal interface
                form.addEventListener("submit", function () {
                    ensureConfirmedHiddenField(form, "true");
                });
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initOutlierGuard);
    } else {
        initOutlierGuard();
    }
})();
