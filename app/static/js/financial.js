/**
 * Financial Reports page logic.
 *
 * Talks to /api/financial/* routes (see app/routers/financial.py).
 */

(function () {
    "use strict";

    var API_BASE = "/api/financial";
    var cashflowTable = null;
    var journalTable = null;
    var OUTLET_RULE_NO = 31; // "Gaji/Upah Tunai" — the only expense rule crediting an outlet-scoped account (1111)

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

    function loadJournal() {
        var p = periodDates();
        return fetch(API_BASE + "/journal?start=" + p.start + "&end=" + p.end)
            .then(function (res) { return res.json(); })
            .then(function (rows) {
                var tableRows = rows.map(function (e) {
                    return [
                        e.no_jurnal, e.tanggal, e.sumber_dokumen,
                        e.kode_debet + " - " + e.nama_akun_debet,
                        e.kode_kredit + " - " + e.nama_akun_kredit,
                        formatRupiah(e.nominal), e.keterangan, e.status,
                    ];
                });

                if (journalTable) {
                    journalTable.clear();
                    journalTable.rows.add(tableRows);
                    journalTable.draw();
                } else {
                    journalTable = $("#journal-datatable").DataTable({
                        data: tableRows,
                        columns: [
                            { title: "No Jurnal" }, { title: "Tanggal" }, { title: "Sumber Dokumen" },
                            { title: "Debet" }, { title: "Kredit" }, { title: "Nominal" },
                            { title: "Keterangan" }, { title: "Status" },
                        ],
                        order: [[1, "desc"]],
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

    function loadExpenseRules() {
        return fetch(API_BASE + "/expense-rules")
            .then(function (res) { return res.json(); })
            .then(function (rules) {
                var select = document.getElementById("expense-rule");
                select.innerHTML = rules.map(function (r) {
                    return "<option value='" + r.no + "'>" + r.event_trigger + " (" +
                        r.kode_debet + " / " + r.kode_kredit + ")</option>";
                }).join("");
                toggleOutletField();
            });
    }

    function loadOutletOptions() {
        return fetch("/api/outlets")
            .then(function (res) { return res.json(); })
            .then(function (outlets) {
                var select = document.getElementById("expense-outlet");
                select.innerHTML = outlets.map(function (o) {
                    return "<option value='" + o.kode_outlet + "'>" + o.nama_outlet + "</option>";
                }).join("");
            });
    }

    function toggleOutletField() {
        var ruleNo = parseInt(document.getElementById("expense-rule").value, 10);
        document.getElementById("expense-outlet-wrapper").classList.toggle("d-none", ruleNo !== OUTLET_RULE_NO);
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
        loadJournal();
    }

    function addExpense() {
        var category = document.getElementById("expense-category").value.trim();
        var ruleNo = parseInt(document.getElementById("expense-rule").value, 10);
        var amount = parseFloat(document.getElementById("expense-amount").value);
        var date = document.getElementById("expense-date").value || todayISO();
        var note = document.getElementById("expense-note").value;
        var outletId = ruleNo === OUTLET_RULE_NO ? document.getElementById("expense-outlet").value : null;

        if (!category || isNaN(amount) || amount <= 0 || isNaN(ruleNo)) {
            alert("Isi kategori, jenis beban, dan jumlah biaya dengan benar.");
            return;
        }
        if (ruleNo === OUTLET_RULE_NO && !outletId) {
            alert("Pilih outlet untuk biaya yang dibayar dari kas tunai.");
            return;
        }

        fetch(API_BASE + "/expenses", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                category: category, amount: amount, note: note, expense_date: date,
                rule_no: ruleNo, outlet_id: outletId,
            }),
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

        loadExpenseRules();
        loadOutletOptions();
        reloadAll();

        document.getElementById("period-select").addEventListener("change", reloadAll);
        document.getElementById("btn-add-expense").addEventListener("click", addExpense);
        document.getElementById("expense-rule").addEventListener("change", toggleOutletField);
    });
})();
