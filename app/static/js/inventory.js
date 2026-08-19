/**
 * Inventory Sync page logic.
 *
 * Talks to /api/inventory/* routes (see app/routers/inventory.py) via plain
 * `fetch`, same pattern as order_inbox.js.
 */

(function () {
    "use strict";

    var API_BASE = "/api/inventory";
    var CHANNEL_BADGE = {
        "Shopee": "badge-channel-shopee text-white",
        "GrabFood": "badge-channel-grabfood text-white",
        "TikTok Shop": "bg-dark text-white",
        "GoFood": "bg-success text-white",
    };

    var dataTable = null;
    var currentSku = null;

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

    function channelBadges(mappings) {
        return mappings.map(function (m) {
            var cls = CHANNEL_BADGE[m.channel] || "bg-secondary text-white";
            return '<span class="badge ' + cls + ' me-1">' + m.channel + "</span>";
        }).join("");
    }

    function renderStats(products) {
        var totalUnits = 0, totalValue = 0, lowStock = 0;
        products.forEach(function (p) {
            totalUnits += p.stock_qty;
            totalValue += p.stock_qty * p.reference_price;
            if (p.is_low_stock) lowStock += 1;
        });
        document.getElementById("stat-total-sku").textContent = products.length;
        document.getElementById("stat-low-stock").textContent = lowStock;
        document.getElementById("stat-total-units").textContent = totalUnits.toLocaleString("id-ID");
        document.getElementById("stat-stock-value").textContent = formatRupiah(totalValue);
    }

    function loadInventory() {
        return fetch(API_BASE)
            .then(function (res) { return res.json(); })
            .then(function (products) {
                renderStats(products);

                var rows = products.map(function (p) {
                    var stockBadge = p.is_low_stock
                        ? '<span class="badge bg-danger-subtle text-danger">' + p.stock_qty + " (menipis)</span>"
                        : '<span class="badge bg-success-subtle text-success">' + p.stock_qty + "</span>";
                    return [
                        p.sku,
                        p.name,
                        channelBadges(p.mappings),
                        stockBadge,
                        formatRupiah(p.reference_price),
                        '<a class="btn btn-sm btn-outline-dark" href="/inventory/' + encodeURIComponent(p.sku) + '">' +
                            '<i class="ri-eye-line"></i> Detail</a> ' +
                            '<button class="btn btn-sm btn-outline-primary btn-adjust" data-sku="' + p.sku +
                            '" data-name="' + p.name + '" data-qty="' + p.stock_qty + '">' +
                            '<i class="ri-edit-line"></i> Sesuaikan</button> ' +
                            '<button class="btn btn-sm btn-outline-secondary btn-history" data-sku="' + p.sku + '">' +
                            '<i class="ri-history-line"></i></button>',
                    ];
                });

                if (dataTable) {
                    dataTable.clear();
                    dataTable.rows.add(rows);
                    dataTable.draw();
                } else {
                    dataTable = $("#inventory-datatable").DataTable({
                        data: rows,
                        columns: [
                            { title: "SKU" }, { title: "Nama Produk" }, { title: "Platform Terhubung" },
                            { title: "Stok" }, { title: "Harga Acuan" }, { title: "Aksi" },
                        ],
                        order: [[0, "asc"]],
                        scrollX: true,
                        scrollY: "360px",
                        scrollCollapse: true,
                        language: {
                            search: "Cari:",
                            lengthMenu: "Tampilkan _MENU_ data",
                            info: "Menampilkan _START_ - _END_ dari _TOTAL_ data",
                            infoEmpty: "Tidak ada data",
                            zeroRecords: "Data tidak ditemukan",
                            paginate: { first: "Pertama", last: "Terakhir", next: "Berikutnya", previous: "Sebelumnya" },
                        },
                    });
                }
            })
            .catch(function (err) { AppNotify.showErrorToast(err, "Gagal memuat data katalog produk."); });
    }

    function openAdjustModal(sku, name, qty) {
        currentSku = sku;
        document.getElementById("adjust-product-name").textContent = name;
        document.getElementById("adjust-product-sku").textContent = "(" + sku + ")";
        document.getElementById("adjust-quantity").value = qty;
        document.getElementById("adjust-note").value = "";
        new bootstrap.Modal(document.getElementById("adjust-stock-modal")).show();
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

        fetch(API_BASE + "/" + encodeURIComponent(currentSku) + "/adjust", {
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
                return loadInventory();
            })
            .catch(function (err) { AppNotify.showErrorToast(err, "Gagal menyesuaikan stok."); })
            .finally(function () { btn.disabled = false; });
    }

    function openHistoryModal(sku) {
        var body = document.getElementById("history-body");
        body.innerHTML = '<div class="text-center text-muted py-4">Memuat...</div>';
        new bootstrap.Modal(document.getElementById("history-modal")).show();

        fetch(API_BASE + "/" + encodeURIComponent(sku) + "/movements")
            .then(function (res) { return res.json(); })
            .then(function (movements) {
                if (movements.length === 0) {
                    body.innerHTML = '<p class="text-muted">Belum ada riwayat pergerakan stok.</p>';
                    return;
                }
                var rows = movements.map(function (m) {
                    var changeText = (m.change_qty > 0 ? "+" : "") + m.change_qty;
                    var sourceLabel = m.source === "order" ? "Pesanan" : "Manual";
                    return "<tr><td>" + formatDateTime(m.created_time) + "</td><td>" + changeText +
                        "</td><td>" + m.resulting_qty + "</td><td>" + sourceLabel +
                        "</td><td>" + (m.note || "-") + "</td></tr>";
                }).join("");
                body.innerHTML =
                    "<table class='table table-sm'><thead><tr><th>Waktu</th><th>Perubahan</th>" +
                    "<th>Stok Akhir</th><th>Sumber</th><th>Catatan</th></tr></thead><tbody>" +
                    rows + "</tbody></table>";
            })
            .catch(function (err) {
                body.innerHTML = '<p class="text-danger mb-0">Gagal memuat riwayat.</p>';
                AppNotify.showErrorToast(err, "Gagal memuat riwayat stok.");
            });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (window.lucide) lucide.createIcons();
        loadInventory();

        document.getElementById("inventory-datatable").addEventListener("click", function (e) {
            var adjustBtn = e.target.closest(".btn-adjust");
            if (adjustBtn) {
                openAdjustModal(adjustBtn.getAttribute("data-sku"), adjustBtn.getAttribute("data-name"), adjustBtn.getAttribute("data-qty"));
                return;
            }
            var historyBtn = e.target.closest(".btn-history");
            if (historyBtn) {
                openHistoryModal(historyBtn.getAttribute("data-sku"));
            }
        });

        document.getElementById("btn-save-adjust").addEventListener("click", saveAdjust);
    });
})();
