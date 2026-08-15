/**
 * Kelola Tim page logic (Customer Request 1 Epic I) — Owner creates and
 * lists their own Admin accounts.
 *
 * Talks to /api/auth/create-admin and /api/auth/admins (see app/routers/auth.py).
 */

(function () {
    "use strict";

    function showListError(message) {
        var el = document.getElementById("admin-error");
        el.textContent = message;
        el.classList.remove("d-none");
    }

    function showFormError(message) {
        var el = document.getElementById("form-admin-error");
        el.textContent = message;
        el.classList.remove("d-none");
    }

    function hideFormError() {
        document.getElementById("form-admin-error").classList.add("d-none");
    }

    function renderAdmins(admins) {
        var body = document.getElementById("admin-list");
        body.innerHTML = admins.length
            ? admins.map(function (a) {
                var statusText = a.is_active ? "Aktif" : "Nonaktif";
                var statusClass = a.is_active ? "text-success" : "text-muted";
                var created = a.created_time ? a.created_time.substring(0, 10) : "-";
                return (
                    "<tr><td>" + a.email + "</td>" +
                    "<td class='" + statusClass + "'>" + statusText + "</td>" +
                    "<td>" + created + "</td></tr>"
                );
            }).join("")
            : "<tr><td colspan='3' class='text-muted'>Belum ada akun Admin.</td></tr>";
    }

    function loadAdmins() {
        return fetch("/api/auth/admins")
            .then(function (res) { return res.json(); })
            .then(renderAdmins)
            .catch(function () { showListError("Gagal memuat daftar Admin."); });
    }

    function createAdmin(email, password) {
        return fetch("/api/auth/create-admin", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email, password: password }),
        }).then(function (res) {
            if (!res.ok) {
                return res.json().then(function (data) {
                    throw new Error(data.detail || "Gagal membuat akun Admin");
                });
            }
            return res.json();
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (window.lucide) lucide.createIcons();
        loadAdmins();

        var form = document.getElementById("form-add-admin");
        form.addEventListener("submit", function (e) {
            e.preventDefault();
            hideFormError();
            var email = document.getElementById("input-admin-email").value.trim();
            var password = document.getElementById("input-admin-password").value;
            if (!email || !password) return;

            createAdmin(email, password)
                .then(function () {
                    form.reset();
                    var modalEl = document.getElementById("modal-add-admin");
                    var modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
                    modal.hide();
                    loadAdmins();
                })
                .catch(function (err) { showFormError(err.message); });
        });
    });
})();
