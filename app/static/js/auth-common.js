/**
 * Shared topbar auth widget — logout button + a small "logged in as ..."
 * label. Included on every authenticated page (Order Inbox, Inventory,
 * Financial, Reconciliation, Platforms).
 *
 * There's no lightweight "who am I" endpoint, so the email is read from the
 * session cookie is NOT accessible client-side (httpOnly-style via
 * SessionMiddleware's signed cookie) — instead each page can optionally set
 * window.CURRENT_USER_EMAIL before this script runs; if not set, the label
 * is just hidden.
 */

(function () {
    "use strict";

    function doLogout() {
        fetch("/api/auth/logout", { method: "POST" })
            .then(function () { window.location.href = "/login"; });
    }

    document.addEventListener("DOMContentLoaded", function () {
        var logoutBtn = document.getElementById("btn-logout");
        if (logoutBtn) {
            logoutBtn.addEventListener("click", function (e) {
                e.preventDefault();
                doLogout();
            });
        }

        var emailLabel = document.getElementById("topbar-user-email");
        if (emailLabel) {
            emailLabel.textContent = window.CURRENT_USER_EMAIL || "Admin";
        }
    });
})();
