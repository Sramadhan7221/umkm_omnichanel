/**
 * Outlet management page logic.
 *
 * Talks to /api/outlets/* routes (see app/routers/outlets.py).
 */

(function () {
    "use strict";

    var API_BASE = "/api/outlets";

    function renderOutlets(outlets) {
        var container = document.getElementById("outlet-list");
        container.innerHTML = outlets.map(function (o) {
            var switchChecked = o.is_active ? "checked" : "";
            var statusText = o.is_active ? "Aktif" : "Nonaktif";
            var statusClass = o.is_active ? "text-success" : "text-muted";

            return (
                '<div class="col-md-6 col-xl-4">' +
                '<div class="card border h-100">' +
                '<div class="card-body">' +
                '<div class="d-flex align-items-start gap-2 mb-2">' +
                '<div class="avatar-sm rounded-circle d-flex align-items-center justify-content-center text-white bg-primary flex-shrink-0" style="width:40px;height:40px;">' +
                '<i class="ri-building-4-line"></i>' +
                '</div>' +
                '<div>' +
                '<h5 class="mb-1">' + o.nama_outlet + '</h5>' +
                '<p class="text-muted mb-0"><small>' + (o.alamat || "-") + '</small></p>' +
                '</div>' +
                '</div>' +
                '<div class="form-check form-switch d-flex align-items-center gap-2">' +
                '<input class="form-check-input outlet-toggle" type="checkbox" role="switch" data-code="' + o.kode_outlet + '" ' + switchChecked + ' style="width:2.5em;height:1.3em;">' +
                '<span class="' + statusClass + ' fw-semibold status-label">' + statusText + '</span>' +
                '</div>' +
                '</div>' +
                '</div>' +
                '</div>'
            );
        }).join("");
    }

    function loadOutlets() {
        return fetch(API_BASE)
            .then(function (res) { return res.json(); })
            .then(renderOutlets);
    }

    function toggle(code, isActive) {
        return fetch(API_BASE + "/" + encodeURIComponent(code) + "/toggle", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ is_active: isActive }),
        });
    }

    function create(namaOutlet, alamat) {
        return fetch(API_BASE, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ nama_outlet: namaOutlet, alamat: alamat }),
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (window.lucide) lucide.createIcons();
        loadOutlets();

        document.getElementById("outlet-list").addEventListener("change", function (e) {
            var checkbox = e.target.closest(".outlet-toggle");
            if (!checkbox) return;

            var code = checkbox.getAttribute("data-code");
            var isActive = checkbox.checked;
            var statusLabel = checkbox.closest(".form-check").querySelector(".status-label");

            toggle(code, isActive).then(function () {
                statusLabel.textContent = isActive ? "Aktif" : "Nonaktif";
                statusLabel.classList.toggle("text-success", isActive);
                statusLabel.classList.toggle("text-muted", !isActive);
            });
        });

        var form = document.getElementById("form-add-outlet");
        form.addEventListener("submit", function (e) {
            e.preventDefault();
            var namaOutlet = document.getElementById("input-nama-outlet").value.trim();
            var alamat = document.getElementById("input-alamat-outlet").value.trim();
            if (!namaOutlet) return;

            create(namaOutlet, alamat).then(function () {
                form.reset();
                var modalEl = document.getElementById("modal-add-outlet");
                var modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
                modal.hide();
                loadOutlets();
            });
        });
    });
})();
