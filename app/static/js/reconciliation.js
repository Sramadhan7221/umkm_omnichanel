/**
 * Reconciliation page logic.
 *
 * Talks to /api/reconciliation/* routes (see app/routers/reconciliation.py).
 */

(function () {
    "use strict";

    var API_BASE = "/api/reconciliation";
    var STATUS_BADGE = {
        "Cocok": "bg-success-subtle text-success",
        "Selisih": "bg-danger-subtle text-danger",
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

    function badge(map, value) {
        var cls = map[value] || "bg-secondary text-white";
        return '<span class="badge ' + cls + '">' + value + "</span>";
    }

    function loadSummary() {
        return fetch(API_BASE + "/summary")
            .then(function (res) { return res.json(); })
            .then(function (data) {
                document.getElementById("stat-total").textContent = data.total_settlements;
                document.getElementById("stat-matched").textContent = data.matched_count;
                document.getElementById("stat-mismatched").textContent = data.mismatched_count;
                document.getElementById("stat-diff").textContent = formatRupiah(data.total_diff);

                var body = document.querySelector("#channel-summary-table tbody");
                body.innerHTML = data.channel_breakdown.length
                    ? data.channel_breakdown.map(function (c) {
                        return "<tr><td>" + badge(CHANNEL_BADGE, c.channel) + "</td><td class='text-end'>" + c.total +
                            "</td><td class='text-end text-success'>" + c.matched +
                            "</td><td class='text-end text-danger'>" + c.mismatched +
                            "</td><td class='text-end'>" + formatRupiah(c.diff) + "</td></tr>";
                    }).join("")
                    : "<tr><td colspan='5' class='text-muted'>Belum ada settlement pada periode ini.</td></tr>";
            });
    }

    function loadSettlements() {
        return fetch(API_BASE + "/settlements")
            .then(function (res) { return res.json(); })
            .then(function (items) {
                var rows = items.map(function (s) {
                    return [
                        s.settlement_id,
                        badge(CHANNEL_BADGE, s.channel),
                        s.platform_order_id,
                        formatRupiah(s.expected_amount),
                        formatRupiah(s.payout_amount),
                        formatRupiah(s.diff_amount),
                        badge(STATUS_BADGE, s.status),
                        formatDateTime(s.settlement_date),
                    ];
                });

                if (dataTable) {
                    dataTable.clear();
                    dataTable.rows.add(rows);
                    dataTable.draw();
                } else {
                    dataTable = $("#settlement-datatable").DataTable({
                        data: rows,
                        columns: [
                            { title: "ID Settlement" }, { title: "Platform" }, { title: "ID Pesanan" },
                            { title: "Ekspektasi" }, { title: "Payout" }, { title: "Selisih" },
                            { title: "Status" }, { title: "Tanggal" },
                        ],
                        order: [[7, "desc"]],
                        responsive: true,
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
            });
    }

    function reloadAll() {
        loadSummary();
        loadSettlements();
    }

    function generateSettlements() {
        var btn = document.getElementById("btn-generate");
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line"></i> Memproses...';

        fetch(API_BASE + "/generate", { method: "POST" })
            .then(function (res) { return res.json(); })
            .then(function () { return reloadAll(); })
            .finally(function () {
                btn.disabled = false;
                btn.innerHTML = '<i class="ri-download-2-line align-middle"></i> Proses Settlement Baru';
            });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (window.lucide) lucide.createIcons();
        reloadAll();

        document.getElementById("btn-generate").addEventListener("click", generateSettlements);
    });
})();
