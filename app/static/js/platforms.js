/**
 * Platform management page logic.
 *
 * Talks to /api/platforms/* routes (see app/routers/platforms.py).
 */

(function () {
    "use strict";

    var API_BASE = "/api/platforms";
    var CHANNEL_BADGE = {
        "shopee": "badge-channel-shopee",
        "grabfood": "badge-channel-grabfood",
        "tiktok_shop": "badge-channel-tiktok_shop",
        "gofood": "badge-channel-gofood",
    };
    var CHANNEL_ICON = {
        "shopee": "ri-shopping-bag-3-line",
        "tiktok_shop": "ri-tiktok-line",
        "grabfood": "ri-motorbike-line",
        "gofood": "ri-restaurant-2-line",
    };

    function renderPlatforms(platforms) {
        var container = document.getElementById("platform-list");
        container.innerHTML = platforms.map(function (p) {
            var badgeClass = CHANNEL_BADGE[p.code] || "bg-secondary";
            var icon = CHANNEL_ICON[p.code] || "ri-plug-line";
            var switchChecked = p.is_active ? "checked" : "";
            var statusText = p.is_active ? "Aktif" : "Nonaktif";
            var statusClass = p.is_active ? "text-success" : "text-muted";

            return (
                '<div class="col-md-6 col-xl-3">' +
                '<div class="card border h-100">' +
                '<div class="card-body text-center">' +
                '<div class="avatar-md mx-auto mb-3 rounded-circle d-flex align-items-center justify-content-center text-white ' + badgeClass + '" style="width:56px;height:56px;">' +
                '<i class="' + icon + '" style="font-size: 1.5rem;"></i>' +
                '</div>' +
                '<h5 class="mb-1">' + p.name + '</h5>' +
                '<p class="text-muted mb-1">' + p.fulfillment_type + '</p>' +
                '<p class="text-muted mb-3"><small>Fee platform: ' + (p.fee_rate != null ? p.fee_rate : 0) + '%</small></p>' +
                '<div class="form-check form-switch d-flex justify-content-center align-items-center gap-2">' +
                '<input class="form-check-input platform-toggle" type="checkbox" role="switch" data-code="' + p.code + '" ' + switchChecked + ' style="width:2.5em;height:1.3em;">' +
                '<span class="' + statusClass + ' fw-semibold status-label">' + statusText + '</span>' +
                '</div>' +
                '</div>' +
                '</div>' +
                '</div>'
            );
        }).join("");
    }

    function loadPlatforms() {
        return fetch(API_BASE)
            .then(function (res) { return res.json(); })
            .then(renderPlatforms);
    }

    function toggle(code, isActive) {
        return fetch(API_BASE + "/" + encodeURIComponent(code) + "/toggle", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ is_active: isActive }),
        }).then(function (res) {
            if (!res.ok) {
                return res.json().then(function (data) {
                    throw new Error(data.detail || "Gagal mengubah status platform");
                });
            }
            return res.json();
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (window.lucide) lucide.createIcons();
        loadPlatforms();

        document.getElementById("platform-list").addEventListener("change", function (e) {
            var checkbox = e.target.closest(".platform-toggle");
            if (!checkbox) return;

            var code = checkbox.getAttribute("data-code");
            var isActive = checkbox.checked;
            var statusLabel = checkbox.closest(".form-check").querySelector(".status-label");

            checkbox.disabled = true;
            toggle(code, isActive)
                .then(function () {
                    statusLabel.textContent = isActive ? "Aktif" : "Nonaktif";
                    statusLabel.classList.toggle("text-success", isActive);
                    statusLabel.classList.toggle("text-muted", !isActive);
                    AppNotify.showSuccessToast(isActive ? "Platform diaktifkan." : "Platform dinonaktifkan.");
                })
                .catch(function (err) {
                    checkbox.checked = !isActive; // revert the switch on failure
                    AppNotify.showErrorToast(err, "Gagal mengubah status platform.");
                })
                .finally(function () { checkbox.disabled = false; });
        });
    });
})();
