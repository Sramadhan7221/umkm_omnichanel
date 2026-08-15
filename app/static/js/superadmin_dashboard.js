/**
 * Superadmin dashboard logic (Customer Request 1 Epic J).
 *
 * Talks to /api/superadmin/* routes (see app/routers/superadmin.py).
 */

(function () {
    "use strict";

    var API_BASE = "/api/superadmin";

    function showPendingError(message) {
        var el = document.getElementById("pending-error");
        el.textContent = message;
        el.classList.remove("d-none");
    }

    function hidePendingError() {
        document.getElementById("pending-error").classList.add("d-none");
    }

    function loadStats() {
        return fetch(API_BASE + "/stats")
            .then(function (res) { return res.json(); })
            .then(function (data) {
                document.getElementById("stat-active-owners").textContent = data.active_owner_count;

                var body = document.getElementById("monthly-owners-table");
                body.innerHTML = data.monthly_new_owners.length
                    ? data.monthly_new_owners.map(function (row) {
                        return "<tr><td>" + row.month + "</td><td class='text-end'>" + row.count + "</td></tr>";
                    }).join("")
                    : "<tr><td colspan='2' class='text-muted'>Belum ada registrasi.</td></tr>";
            });
    }

    function renderPending(owners) {
        var body = document.getElementById("pending-owners-table");
        body.innerHTML = owners.length
            ? owners.map(function (o) {
                var created = o.created_time ? o.created_time.substring(0, 10) : "-";
                return (
                    "<tr>" +
                    "<td>" + o.business_name + "</td>" +
                    "<td>" + o.email + "</td>" +
                    "<td>" + created + "</td>" +
                    "<td class='text-end'>" +
                    "<button class='btn btn-sm btn-success me-1 btn-approve' data-id='" + o.id + "'>Setujui</button>" +
                    "<button class='btn btn-sm btn-outline-danger btn-reject' data-id='" + o.id + "'>Tolak</button>" +
                    "</td>" +
                    "</tr>"
                );
            }).join("")
            : "<tr><td colspan='4' class='text-muted'>Tidak ada registrasi menunggu.</td></tr>";
    }

    function loadPending() {
        return fetch(API_BASE + "/owners/pending")
            .then(function (res) { return res.json(); })
            .then(renderPending);
    }

    function decide(id, action) {
        hidePendingError();
        return fetch(API_BASE + "/users/" + id + "/" + action, { method: "POST" })
            .then(function (res) {
                if (!res.ok) {
                    return res.json().then(function (data) {
                        throw new Error(data.detail || "Gagal memproses");
                    });
                }
            })
            .then(function () {
                loadPending();
                loadStats();
            })
            .catch(function (err) { showPendingError(err.message); });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (window.lucide) lucide.createIcons();
        loadStats();
        loadPending();

        document.getElementById("pending-owners-table").addEventListener("click", function (e) {
            var approveBtn = e.target.closest(".btn-approve");
            var rejectBtn = e.target.closest(".btn-reject");
            if (approveBtn) decide(approveBtn.getAttribute("data-id"), "approve");
            if (rejectBtn) decide(rejectBtn.getAttribute("data-id"), "reject");
        });
    });
})();
