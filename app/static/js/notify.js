/**
 * Centralized notification helpers — Bootstrap 5 Toast for success/error
 * feedback, Bootstrap 5 Modal for confirming destructive/consequential
 * actions. Every page includes this before its own script so create/update/
 * delete flows all look and behave the same way (see docs/CLAUDE.md).
 *
 * Usage:
 *   AppNotify.showSuccessToast("Data berhasil disimpan.");
 *   AppNotify.showErrorToast(err, "Gagal menyimpan data.");
 *   AppNotify.confirmAction({ title, message, confirmText, variant }).then(...)
 *   AppNotify.confirmDelete("produk 'Kopi Susu'").then(function (ok) { ... });
 */
(function (global) {
    "use strict";

    var TOAST_DELAY_MS = 4000;

    function ensureToastContainer() {
        var container = document.getElementById("app-toast-container");
        if (!container) {
            container = document.createElement("div");
            container.id = "app-toast-container";
            container.className = "toast-container position-fixed p-3";
            container.style.top = "5rem";
            container.style.right = "0";
            container.style.zIndex = "1080";
            document.body.appendChild(container);
        }
        return container;
    }

    function showToast(message, variant) {
        var container = ensureToastContainer();
        var el = document.createElement("div");
        el.className = "toast align-items-center text-bg-" + variant + " border-0";
        el.setAttribute("role", "alert");
        el.setAttribute("aria-live", "assertive");
        el.setAttribute("aria-atomic", "true");
        el.innerHTML =
            '<div class="d-flex">' +
                '<div class="toast-body"></div>' +
                '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>' +
            "</div>";
        el.querySelector(".toast-body").textContent = message;
        container.appendChild(el);

        var toast = new bootstrap.Toast(el, { delay: TOAST_DELAY_MS });
        el.addEventListener("hidden.bs.toast", function () { el.remove(); });
        toast.show();
        return toast;
    }

    function showSuccessToast(message) {
        return showToast(message || "Berhasil.", "success");
    }

    function showWarningToast(message) {
        return showToast(message || "Perhatian.", "warning");
    }

    /**
     * err can be an Error, a plain string, or omitted. Falls back to a
     * generic message so a raw exception never leaks straight to the user.
     */
    function showErrorToast(err, fallback) {
        var message = fallback || "Terjadi kesalahan. Silakan coba lagi.";
        if (typeof err === "string" && err) {
            message = err;
        } else if (err && err.message) {
            message = err.message;
        }
        return showToast(message, "danger");
    }

    /**
     * Shows a confirmation modal and resolves true/false depending on the
     * user's choice. Used before any destructive or hard-to-reverse action
     * (delete, reject, deactivate, close-month, process-retur, ...).
     */
    function confirmAction(options) {
        options = options || {};
        var title = options.title || "Konfirmasi";
        var message = options.message || "Apakah Anda yakin?";
        var confirmText = options.confirmText || "Ya, Lanjutkan";
        var cancelText = options.cancelText || "Batal";
        var variant = options.variant === "danger" ? "danger" : "primary";

        return new Promise(function (resolve) {
            var modalEl = document.createElement("div");
            modalEl.className = "modal fade";
            modalEl.tabIndex = -1;
            modalEl.setAttribute("aria-hidden", "true");
            modalEl.innerHTML =
                '<div class="modal-dialog modal-dialog-centered">' +
                    '<div class="modal-content">' +
                        '<div class="modal-header">' +
                            '<h5 class="modal-title"></h5>' +
                            '<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>' +
                        "</div>" +
                        '<div class="modal-body"></div>' +
                        '<div class="modal-footer">' +
                            '<button type="button" class="btn btn-light" data-action="cancel"></button>' +
                            '<button type="button" class="btn" data-action="confirm"></button>' +
                        "</div>" +
                    "</div>" +
                "</div>";

            modalEl.querySelector(".modal-title").textContent = title;
            modalEl.querySelector(".modal-body").textContent = message;
            var cancelBtn = modalEl.querySelector('[data-action="cancel"]');
            var confirmBtn = modalEl.querySelector('[data-action="confirm"]');
            cancelBtn.textContent = cancelText;
            confirmBtn.textContent = confirmText;
            confirmBtn.classList.add("btn-" + variant);

            document.body.appendChild(modalEl);
            var modal = new bootstrap.Modal(modalEl);
            var settled = false;

            confirmBtn.addEventListener("click", function () {
                settled = true;
                modal.hide();
                resolve(true);
            });

            modalEl.addEventListener("hidden.bs.modal", function () {
                modalEl.remove();
                if (!settled) resolve(false);
            });

            modal.show();
        });
    }

    var FLASH_STORAGE_KEY = "appNotifyFlash";

    /**
     * Stashes a success message to show right after the next page load —
     * for flows that redirect immediately on success (e.g. save product ->
     * navigate to its detail page), where a toast fired just before
     * navigating would never be seen.
     */
    function flashSuccessOnNextLoad(message) {
        try {
            sessionStorage.setItem(FLASH_STORAGE_KEY, message);
        } catch (e) {
            // sessionStorage unavailable (e.g. private mode) — message is just lost, non-fatal.
        }
    }

    function consumeFlash() {
        var message;
        try {
            message = sessionStorage.getItem(FLASH_STORAGE_KEY);
            if (message) sessionStorage.removeItem(FLASH_STORAGE_KEY);
        } catch (e) {
            return;
        }
        if (message) showSuccessToast(message);
    }

    document.addEventListener("DOMContentLoaded", consumeFlash);

    function confirmDelete(itemLabel) {
        return confirmAction({
            title: "Hapus Data",
            message: "Apakah Anda yakin ingin menghapus " + (itemLabel || "data ini") +
                "? Tindakan ini tidak dapat dibatalkan.",
            confirmText: "Ya, Hapus",
            variant: "danger",
        });
    }

    global.AppNotify = {
        showSuccessToast: showSuccessToast,
        showErrorToast: showErrorToast,
        showWarningToast: showWarningToast,
        confirmAction: confirmAction,
        confirmDelete: confirmDelete,
        flashSuccessOnNextLoad: flashSuccessOnNextLoad,
    };
})(window);
