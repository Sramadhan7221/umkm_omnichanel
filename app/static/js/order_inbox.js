/**
 * Order Inbox page logic.
 *
 * Talks to the FastAPI backend via plain `fetch` against /api/* routes
 * (see app/routers/api.py). No CSRF handling needed — FastAPI doesn't
 * require it by default and this demo has no auth layer.
 */

(function () {
    "use strict";

    var API_BASE = "/api/";
    var STATUS_BADGE = {
        "Baru": "bg-info-subtle text-info",
        "Diterima": "bg-primary-subtle text-primary",
        "Diproses": "bg-warning-subtle text-warning",
        "Siap Diambil": "bg-warning-subtle text-warning",
        "Dikirim": "bg-primary-subtle text-primary",
        "Selesai": "bg-success-subtle text-success",
        "Dibatalkan": "bg-danger-subtle text-danger",
        "Dikembalikan": "bg-danger-subtle text-danger",
    };
    var CHANNEL_BADGE = {
        "Shopee": "badge-channel-shopee text-white",
        "GrabFood": "badge-channel-grabfood text-white",
        "TikTok Shop": "bg-dark text-white",
        "GoFood": "bg-success text-white",
    };

    var dataTable = null;

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

    function badge(map, value, extraClass) {
        var cls = map[value] || "bg-secondary text-white";
        return '<span class="badge ' + cls + " " + (extraClass || "") + '">' + value + "</span>";
    }

    function renderStats(orders) {
        var gross = 0, net = 0;
        orders.forEach(function (o) {
            gross += Number(o.gross_amount || 0);
            net += Number(o.net_amount || 0);
        });
        document.getElementById("stat-total").textContent = orders.length;
        document.getElementById("stat-gross").textContent = formatRupiah(gross);
        document.getElementById("stat-net").textContent = formatRupiah(net);
        document.getElementById("stat-fees").textContent = formatRupiah(gross - net);
    }

    function loadOrderInbox() {
        return fetch(API_BASE + "order-inbox")
            .then(function (res) { return res.json(); })
            .then(function (orders) {
                renderStats(orders);

                var rows = orders.map(function (o) {
                    return [
                        badge(CHANNEL_BADGE, o.channel),
                        '<span class="badge-fulfillment">' + o.fulfillment_type + "</span>",
                        badge(STATUS_BADGE, o.status),
                        o.platform_order_id,
                        formatDateTime(o.order_time),
                        formatRupiah(o.gross_amount),
                        formatRupiah(o.net_amount),
                        '<button class="btn btn-sm btn-outline-primary btn-detail" data-name="' +
                            o.name + '"><i class="ri-eye-line"></i></button>',
                    ];
                });

                if (dataTable) {
                    dataTable.clear();
                    dataTable.rows.add(rows);
                    dataTable.draw();
                } else {
                    dataTable = $("#order-inbox-datatable").DataTable({
                        data: rows,
                        columns: [
                            { title: "Platform" }, { title: "Jenis Pemenuhan" }, { title: "Status" },
                            { title: "ID Pesanan Platform" }, { title: "Waktu Pesanan" },
                            { title: "Kotor" }, { title: "Bersih" }, { title: "Detail" },
                        ],
                        order: [[4, "desc"]],
                        responsive: true,
                        language: {
                            search: "Cari:",
                            lengthMenu: "Tampilkan _MENU_ data",
                            info: "Menampilkan _START_ - _END_ dari _TOTAL_ data",
                            infoEmpty: "Tidak ada data",
                            infoFiltered: "(disaring dari _MAX_ total data)",
                            zeroRecords: "Data tidak ditemukan",
                            paginate: { first: "Pertama", last: "Terakhir", next: "Berikutnya", previous: "Sebelumnya" },
                        },
                    });
                }
            });
    }

    function showOrderDetail(name) {
        var modalBody = document.getElementById("order-detail-body");
        modalBody.innerHTML = '<div class="text-center text-muted py-4">Memuat...</div>';
        var modalEl = document.getElementById("order-detail-modal");
        var modal = new bootstrap.Modal(modalEl);
        modal.show();

        fetch(API_BASE + "order/" + encodeURIComponent(name))
            .then(function (res) { return res.json(); })
            .then(function (o) {
                var itemsHtml = o.items.map(function (i) {
                    return "<tr><td>" + i.item_name + " (" + i.sku + ")</td><td>" + i.quantity +
                        "</td><td>" + formatRupiah(i.unit_price) + "</td><td>" + (i.modifiers || "-") + "</td></tr>";
                }).join("");
                var feesHtml = o.fees.map(function (f) {
                    return "<tr><td>" + f.category + "</td><td>" + formatRupiah(f.amount) +
                        "</td><td class='text-muted'>" + f.label + "</td></tr>";
                }).join("");

                modalBody.innerHTML =
                    "<div class='mb-3'>" +
                    "<strong>" + o.platform_order_id + "</strong> &middot; " + o.channel +
                    " &middot; " + o.fulfillment_type +
                    "<br><span class='text-muted'>Status: " + o.status + " (asli: " + o.raw_status + ")</span>" +
                    "<br><span class='text-muted'>Waktu pesanan: " + formatDateTime(o.order_time) + "</span>" +
                    "</div>" +
                    "<h6>Item</h6>" +
                    "<table class='table table-sm'><thead><tr><th>Item</th><th>Jumlah</th><th>Harga Satuan</th><th>Catatan</th></tr></thead><tbody>" +
                    itemsHtml + "</tbody></table>" +
                    "<h6 class='mt-3'>Biaya</h6>" +
                    "<table class='table table-sm'><thead><tr><th>Kategori</th><th>Jumlah</th><th>Label Asli Platform</th></tr></thead><tbody>" +
                    feesHtml + "</tbody></table>" +
                    "<div class='text-end'><strong>Kotor: " + formatRupiah(o.gross_amount) +
                    " &nbsp;|&nbsp; Bersih: " + formatRupiah(o.net_amount) + "</strong></div>";
            });
    }

    function renderSyncResult(result) {
        var box = document.getElementById("sync-result");
        if (!box) return;

        var entries = Object.entries(result || {});
        if (entries.length === 0) {
            box.innerHTML = '<div class="alert alert-warning mb-3">Tidak ada platform aktif. Aktifkan platform di menu <a href="/platforms">Platform</a>.</div>';
            return;
        }

        var items = entries.map(function (entry) {
            var isSuccess = /pesanan baru/.test(entry[1]);
            var icon = isSuccess ? "ri-checkbox-circle-line text-success" : "ri-error-warning-line text-warning";
            return "<li><i class='" + icon + "'></i> <strong>" + entry[0] + "</strong>: " + entry[1] + "</li>";
        }).join("");

        box.innerHTML = '<div class="alert alert-info mb-3"><ul class="mb-0 list-unstyled">' + items + "</ul></div>";
    }

    function syncMockOrders() {
        var btn = document.getElementById("btn-sync");
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line"></i> Menyinkronkan...';

        fetch(API_BASE + "sync-mock-orders", { method: "POST" })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                renderSyncResult(data.result);
                return loadOrderInbox();
            })
            .finally(function () {
                btn.disabled = false;
                btn.innerHTML = '<i class="ri-refresh-line align-middle"></i> Sinkronkan Pesanan';
            });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (window.lucide) lucide.createIcons();
        loadOrderInbox();

        document.getElementById("btn-sync").addEventListener("click", syncMockOrders);

        document.getElementById("order-inbox-datatable").addEventListener("click", function (e) {
            var btn = e.target.closest(".btn-detail");
            if (btn) showOrderDetail(btn.getAttribute("data-name"));
        });
    });
})();