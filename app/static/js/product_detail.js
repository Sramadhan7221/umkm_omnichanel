/**
 * Detail Produk page logic (Fase 6) — marketplace-style single-page view.
 */

(function () {
    "use strict";

    var SKU = window.PRODUCT_DETAIL_SKU;
    var API_BASE = "/api/inventory";
    var CHANNEL_BADGE = {
        "Shopee": "badge-channel-shopee text-white",
        "GrabFood": "badge-channel-grabfood text-white",
        "TikTok Shop": "bg-dark text-white",
        "GoFood": "bg-success text-white",
    };
    var platformFeeByName = {};

    function formatRupiah(amount) {
        var n = Number(amount || 0);
        return "Rp " + n.toLocaleString("id-ID", { maximumFractionDigits: 0 });
    }

    function formatDateTime(value) {
        if (!value) return "-";
        var d = new Date(value.replace(" ", "T"));
        if (isNaN(d.getTime())) return value;
        return d.toLocaleString("id-ID", {
            day: "2-digit", month: "short", year: "numeric",
            hour: "2-digit", minute: "2-digit",
        });
    }

    function setMainImage(url) {
        var wrap = document.getElementById("main-image-wrap");
        if (url) {
            wrap.innerHTML = '<img src="' + url + '" class="product-main-image" alt="foto produk">';
        } else {
            wrap.innerHTML = '<div class="no-image-placeholder"><i class="ri-image-line" style="font-size:2.5rem;"></i></div>';
        }
    }

    function renderImages(images) {
        var primary = images.find(function (i) { return i.is_primary; }) || images[0];
        setMainImage(primary ? primary.url : null);

        var strip = document.getElementById("thumbnail-strip");
        strip.innerHTML = images.map(function (img, idx) {
            return '<img src="' + img.url + '" class="product-thumb' + (img === primary ? " active" : "") +
                '" data-url="' + img.url + '">';
        }).join("");

        strip.querySelectorAll(".product-thumb").forEach(function (thumb) {
            thumb.addEventListener("click", function () {
                setMainImage(thumb.getAttribute("data-url"));
                strip.querySelectorAll(".product-thumb").forEach(function (t) { t.classList.remove("active"); });
                thumb.classList.add("active");
            });
        });
    }

    function renderPlatforms(mappings) {
        var container = document.getElementById("d-platforms");
        if (mappings.length === 0) {
            container.innerHTML = '<span class="text-muted">Belum dipetakan ke platform manapun.</span>';
            return;
        }
        container.innerHTML = mappings.map(function (m) {
            var cls = CHANNEL_BADGE[m.channel] || "bg-secondary text-white";
            var fee = platformFeeByName[m.channel];
            var feeText = fee != null ? " &middot; Fee " + fee + "%" : "";
            return '<span class="badge ' + cls + ' me-2 mb-2 p-2">' + m.channel + feeText + "</span>";
        }).join("");
    }

    function renderAuditLog(logs) {
        var container = document.getElementById("audit-log-list");
        if (logs.length === 0) {
            container.innerHTML = '<p class="text-muted mb-0">Belum ada perubahan tercatat.</p>';
            return;
        }
        container.innerHTML = logs.map(function (log) {
            var rows = Object.keys(log.changed_fields).map(function (field) {
                var change = log.changed_fields[field];
                return "<li><strong>" + field + ":</strong> " + change.old + " &rarr; " + change.new + "</li>";
            }).join("");
            return (
                "<div class='mb-3 pb-2 border-bottom'>" +
                "<div class='text-muted small'>" + formatDateTime(log.changed_time) +
                (log.note ? " &middot; " + log.note : "") + "</div>" +
                "<ul class='mb-0 ps-3'>" + rows + "</ul>" +
                "</div>"
            );
        }).join("");
    }

    function renderMovements(movements) {
        var body = document.querySelector("#movements-table tbody");
        if (movements.length === 0) {
            body.innerHTML = "<tr><td colspan='4' class='text-muted'>Belum ada riwayat.</td></tr>";
            return;
        }
        body.innerHTML = movements.map(function (m) {
            var changeText = (m.change_qty > 0 ? "+" : "") + m.change_qty;
            var sourceLabel = m.source === "order" ? "Pesanan" : "Manual";
            return "<tr><td>" + formatDateTime(m.created_time) + "</td><td>" + changeText +
                "</td><td>" + m.resulting_qty + "</td><td>" + sourceLabel + "</td></tr>";
        }).join("");
    }

    function loadPlatformFees() {
        return fetch("/api/platforms")
            .then(function (res) { return res.json(); })
            .then(function (platforms) {
                platforms.forEach(function (p) { platformFeeByName[p.name] = p.fee_rate; });
            });
    }

    function loadDetail() {
        return fetch(API_BASE + "/products/" + encodeURIComponent(SKU) + "/detail")
            .then(function (res) { return res.json(); })
            .then(function (p) {
                document.getElementById("d-name").textContent = p.name;
                document.getElementById("d-sku").textContent = "SKU: " + p.sku;

                var isLow = p.stock_qty <= p.low_stock_threshold;
                var stockBadge = document.getElementById("d-stock-badge");
                stockBadge.className = "badge " + (isLow ? "bg-danger-subtle text-danger" : "bg-success-subtle text-success");
                stockBadge.textContent = "Stok: " + p.stock_qty;

                document.getElementById("d-price").textContent = formatRupiah(p.reference_price);
                var ppnAmount = p.reference_price * (p.ppn_rate / 100);
                document.getElementById("d-price-breakdown").innerHTML =
                    "Harga dasar " + formatRupiah(p.reference_price) + " + PPN " + p.ppn_rate + "% (" +
                    formatRupiah(ppnAmount) + ") = <strong>" + formatRupiah(p.reference_price + ppnAmount) + "</strong>";

                document.getElementById("d-hpp-unit").innerHTML =
                    "HPP: <strong>" + formatRupiah(p.cogs_price) + "</strong> &middot; Satuan: <strong>" + p.unit_label + "</strong>";

                document.getElementById("d-description").textContent = p.description || "Belum ada deskripsi.";

                renderImages(p.images || []);
                renderPlatforms(p.mappings || []);

                document.getElementById("btn-edit-product").setAttribute("href", "/inventory/" + encodeURIComponent(p.sku) + "/edit");
                document.getElementById("adjust-quantity").value = p.stock_qty;
            });
    }

    function loadMovements() {
        return fetch(API_BASE + "/" + encodeURIComponent(SKU) + "/movements")
            .then(function (res) { return res.json(); })
            .then(renderMovements);
    }

    function loadAuditLog() {
        return fetch(API_BASE + "/products/" + encodeURIComponent(SKU) + "/audit")
            .then(function (res) { return res.json(); })
            .then(renderAuditLog);
    }

    function saveAdjust() {
        var qty = parseInt(document.getElementById("adjust-quantity").value, 10);
        var note = document.getElementById("adjust-note").value;
        if (isNaN(qty) || qty < 0) {
            AppNotify.showWarningToast("Isi stok baru dengan angka yang valid.");
            return;
        }

        var btn = document.getElementById("btn-save-adjust");
        btn.disabled = true;

        fetch(API_BASE + "/" + encodeURIComponent(SKU) + "/adjust", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ quantity: qty, note: note }),
        })
            .then(function (res) {
                if (!res.ok) return res.json().then(function (body) { throw new Error(body.detail || "Gagal menyesuaikan stok"); });
                return res.json();
            })
            .then(function () {
                bootstrap.Modal.getInstance(document.getElementById("adjust-stock-modal")).hide();
                AppNotify.showSuccessToast("Stok berhasil disesuaikan.");
                return Promise.all([loadDetail(), loadMovements(), loadAuditLog()]);
            })
            .catch(function (err) { AppNotify.showErrorToast(err, "Gagal menyesuaikan stok."); })
            .finally(function () { btn.disabled = false; });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (window.lucide) lucide.createIcons();

        loadPlatformFees()
            .then(loadDetail)
            .then(loadMovements)
            .then(loadAuditLog)
            .catch(function (err) { AppNotify.showErrorToast(err, "Gagal memuat data produk."); });

        document.getElementById("btn-quick-adjust").addEventListener("click", function () {
            new bootstrap.Modal(document.getElementById("adjust-stock-modal")).show();
        });
        document.getElementById("btn-save-adjust").addEventListener("click", saveAdjust);
    });
})();
