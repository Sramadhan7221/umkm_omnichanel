/**
 * Financial Reports page logic.
 *
 * Talks to /api/financial/* routes (see app/routers/financial.py).
 */

(function () {
    "use strict";

    var API_BASE = "/api/financial";
    var cashflowTable = null;

    function formatRupiah(amount) {
        var n = Number(amount || 0);
        return "Rp " + n.toLocaleString("id-ID", { maximumFractionDigits: 0 });
    }

    function todayISO() {
        return new Date().toISOString().slice(0, 10);
    }

    function periodDates() {
        var days = parseInt(document.getElementById("period-select").value, 10);
        var end = new Date();
        var start = new Date();
        start.setDate(start.getDate() - days);
        return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) };
    }

    function loadIncomeStatement() {
        var p = periodDates();
        return fetch(API_BASE + "/income-statement?start=" + p.start + "&end=" + p.end)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                document.getElementById("stat-gross").textContent = formatRupiah(data.gross_revenue);
                document.getElementById("stat-order-count").textContent = data.order_count + " pesanan";
                document.getElementById("stat-fees").textContent = formatRupiah(data.total_fees);
                document.getElementById("stat-net").textContent = formatRupiah(data.net_revenue);
                document.getElementById("stat-profit").textContent = formatRupiah(data.net_profit);

                var feeBody = document.querySelector("#fee-breakdown-table tbody");
                var feeEntries = Object.entries(data.fees_by_category);
                feeBody.innerHTML = feeEntries.length
                    ? feeEntries.map(function (entry) {
                        return "<tr><td>" + entry[0] + "</td><td class='text-end'>" + formatRupiah(entry[1]) + "</td></tr>";
                    }).join("")
                    : "<tr><td colspan='2' class='text-muted'>Tidak ada data pada periode ini.</td></tr>";

                var channelBody = document.querySelector("#channel-breakdown-table tbody");
                channelBody.innerHTML = data.channel_breakdown.length
                    ? data.channel_breakdown.map(function (c) {
                        return "<tr><td>" + c.channel + "</td><td class='text-end'>" + c.count +
                            "</td><td class='text-end'>" + formatRupiah(c.gross) +
                            "</td><td class='text-end'>" + formatRupiah(c.net) + "</td></tr>";
                    }).join("")
                    : "<tr><td colspan='4' class='text-muted'>Tidak ada data pada periode ini.</td></tr>";
            });
    }

    function loadCashFlow() {
        var p = periodDates();
        return fetch(API_BASE + "/cash-flow?start=" + p.start + "&end=" + p.end)
            .then(function (res) { return res.json(); })
            .then(function (rows) {
                var tableRows = rows.map(function (r) {
                    return [r.date, formatRupiah(r.cash_in), formatRupiah(r.cash_out), formatRupiah(r.net)];
                });

                if (cashflowTable) {
                    cashflowTable.clear();
                    cashflowTable.rows.add(tableRows);
                    cashflowTable.draw();
                } else {
                    cashflowTable = $("#cashflow-datatable").DataTable({
                        data: tableRows,
                        columns: [
                            { title: "Tanggal" }, { title: "Kas Masuk" }, { title: "Kas Keluar" }, { title: "Kas Bersih" },
                        ],
                        order: [[0, "desc"]],
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

    function loadExpenses() {
        var p = periodDates();
        return fetch(API_BASE + "/expenses?start=" + p.start + "&end=" + p.end)
            .then(function (res) { return res.json(); })
            .then(function (items) {
                var body = document.querySelector("#expense-table tbody");
                body.innerHTML = items.length
                    ? items.map(function (e) {
                        return "<tr><td>" + e.expense_date + "</td><td>" + e.category +
                            "</td><td class='text-end'>" + formatRupiah(e.amount) +
                            "</td><td>" + (e.note || "-") + "</td></tr>";
                    }).join("")
                    : "<tr><td colspan='4' class='text-muted'>Belum ada biaya tercatat pada periode ini.</td></tr>";
            });
    }

    function reloadAll() {
        loadIncomeStatement();
        loadCashFlow();
        loadExpenses();
    }

    function addExpense() {
        var category = document.getElementById("expense-category").value.trim();
        var amount = parseFloat(document.getElementById("expense-amount").value);
        var date = document.getElementById("expense-date").value || todayISO();
        var note = document.getElementById("expense-note").value;

        if (!category || isNaN(amount) || amount <= 0) {
            alert("Isi kategori dan jumlah biaya dengan benar.");
            return;
        }

        fetch(API_BASE + "/expenses", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ category: category, amount: amount, note: note, expense_date: date }),
        })
            .then(function (res) { return res.json(); })
            .then(function () {
                document.getElementById("expense-category").value = "";
                document.getElementById("expense-amount").value = "";
                document.getElementById("expense-note").value = "";
                reloadAll();
            });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (window.lucide) lucide.createIcons();
        document.getElementById("expense-date").value = todayISO();

        reloadAll();

        document.getElementById("period-select").addEventListener("change", reloadAll);
        document.getElementById("btn-add-expense").addEventListener("click", addExpense);
    });
})();
