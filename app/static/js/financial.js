/**
 * Financial Reports page logic.
 *
 * Talks to /api/financial/* routes (see app/routers/financial.py).
 */

(function () {
    "use strict";

    var API_BASE = "/api/financial";
    var journalTable = null;

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

    function loadProfitLoss() {
        var p = periodDates();
        return fetch(API_BASE + "/profit-loss?start=" + p.start + "&end=" + p.end)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                document.getElementById("stat-revenue").textContent = formatRupiah(data.total_pendapatan);
                document.getElementById("stat-hpp").textContent = formatRupiah(data.hpp);
                document.getElementById("stat-gross-profit").textContent = formatRupiah(data.laba_kotor);
                document.getElementById("stat-profit").textContent = formatRupiah(data.laba_bersih);

                var bebanBody = document.querySelector("#beban-breakdown-table tbody");
                bebanBody.innerHTML = data.beban_operasional_breakdown.length
                    ? data.beban_operasional_breakdown.map(function (item) {
                        return "<tr><td>" + item.kode_akun + " - " + item.nama_akun +
                            "</td><td class='text-end'>" + formatRupiah(item.jumlah) + "</td></tr>";
                    }).join("")
                    : "<tr><td colspan='2' class='text-muted'>Tidak ada beban pada periode ini.</td></tr>";
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
            });
    }

    function currentPeriod() {
        return document.getElementById("pph-period").value || todayISO().slice(0, 7);
    }

    function loadPphSummary() {
        return fetch(API_BASE + "/pph/summary?period=" + currentPeriod())
            .then(function (res) { return res.json(); })
            .then(function (data) {
                document.getElementById("pph-estimate").textContent = formatRupiah(data.estimated_pph);
                document.getElementById("pph-outstanding").textContent = formatRupiah(data.outstanding_utang);

                var badge = document.getElementById("pph-status");
                badge.textContent = data.status;
                badge.className = "badge " + (
                    data.status === "Sudah Disetor" ? "bg-success" :
                    data.status === "Belum Disetor" ? "bg-warning" : "bg-secondary"
                );

                var closeBtn = document.getElementById("btn-close-month-pph");
                closeBtn.disabled = data.is_accrued;
                closeBtn.textContent = data.is_accrued ? "Sudah Ditutup Buku" : "Tutup Buku Bulan Ini";
            });
    }

    function closeMonthPph() {
        AppNotify.confirmAction({
            title: "Tutup Buku Bulan Ini",
            message: "Setelah ditutup, PPh Final periode " + currentPeriod() + " tidak bisa diubah lagi. Lanjutkan?",
            confirmText: "Ya, Tutup Buku",
            variant: "danger",
        }).then(function (confirmed) {
            if (!confirmed) return;

            var btn = document.getElementById("btn-close-month-pph");
            btn.disabled = true;

            fetch(API_BASE + "/pph/close-month", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ period: currentPeriod() }),
            })
                .then(function (res) {
                    if (!res.ok) return res.json().then(function (body) { throw new Error(body.detail || "Gagal tutup buku"); });
                    return res.json();
                })
                .then(function () {
                    AppNotify.showSuccessToast("Buku bulan ini berhasil ditutup.");
                    loadPphSummary();
                    loadJournal();
                })
                .catch(function (err) {
                    AppNotify.showErrorToast(err, "Gagal tutup buku.");
                    btn.disabled = false;
                });
        });
    }

    function depositPph() {
        var amount = parseFloat(document.getElementById("pph-deposit-amount").value);
        var date = document.getElementById("pph-deposit-date").value || todayISO();

        if (isNaN(amount) || amount <= 0) {
            AppNotify.showWarningToast("Isi jumlah setoran dengan benar.");
            return;
        }

        var btn = document.getElementById("btn-deposit-pph");
        btn.disabled = true;

        fetch(API_BASE + "/pph/deposit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ amount: amount, deposit_date: date }),
        })
            .then(function (res) {
                if (!res.ok) return res.json().then(function (body) { throw new Error(body.detail || "Gagal mencatat setoran"); });
                return res.json();
            })
            .then(function () {
                document.getElementById("pph-deposit-amount").value = "";
                AppNotify.showSuccessToast("Setoran PPh berhasil dicatat.");
                loadPphSummary();
                loadJournal();
            })
            .catch(function (err) { AppNotify.showErrorToast(err, "Gagal mencatat setoran."); })
            .finally(function () { btn.disabled = false; });
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

    function exportReport(kind, format) {
        var p = periodDates();
        window.location.href = API_BASE + "/" + kind + "/export?start=" + p.start + "&end=" + p.end + "&format=" + format;
    }

    function reloadAll() {
        loadProfitLoss();
        loadExpenses();
        loadJournal();
    }

    function addExpense() {
        var category = document.getElementById("expense-category").value.trim();
        var ruleNo = parseInt(document.getElementById("expense-rule").value, 10);
        var amount = parseFloat(document.getElementById("expense-amount").value);
        var date = document.getElementById("expense-date").value || todayISO();
        var note = document.getElementById("expense-note").value;

        if (!category || isNaN(amount) || amount <= 0 || isNaN(ruleNo)) {
            AppNotify.showWarningToast("Isi kategori, jenis beban, dan jumlah biaya dengan benar.");
            return;
        }

        var btn = document.getElementById("btn-add-expense");
        btn.disabled = true;

        fetch(API_BASE + "/expenses", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                category: category, amount: amount, note: note, expense_date: date,
                rule_no: ruleNo,
            }),
        })
            .then(function (res) {
                if (!res.ok) return res.json().then(function (body) { throw new Error(body.detail || "Gagal mencatat biaya"); });
                return res.json();
            })
            .then(function () {
                document.getElementById("expense-category").value = "";
                document.getElementById("expense-amount").value = "";
                document.getElementById("expense-note").value = "";
                AppNotify.showSuccessToast("Biaya operasional berhasil dicatat.");
                reloadAll();
            })
            .catch(function (err) { AppNotify.showErrorToast(err, "Gagal mencatat biaya."); })
            .finally(function () { btn.disabled = false; });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (window.lucide) lucide.createIcons();
        document.getElementById("expense-date").value = todayISO();
        document.getElementById("pph-period").value = todayISO().slice(0, 7);
        document.getElementById("pph-deposit-date").value = todayISO();

        loadExpenseRules();
        loadPphSummary();
        reloadAll();

        document.getElementById("period-select").addEventListener("change", reloadAll);
        document.getElementById("btn-add-expense").addEventListener("click", addExpense);
        document.getElementById("pph-period").addEventListener("change", loadPphSummary);
        document.getElementById("btn-close-month-pph").addEventListener("click", closeMonthPph);
        document.getElementById("btn-deposit-pph").addEventListener("click", depositPph);

        document.getElementById("btn-export-pl-xlsx").addEventListener("click", function (e) {
            e.preventDefault(); exportReport("profit-loss", "xlsx");
        });
        document.getElementById("btn-export-pl-pdf").addEventListener("click", function (e) {
            e.preventDefault(); exportReport("profit-loss", "pdf");
        });
        document.getElementById("btn-export-journal-xlsx").addEventListener("click", function (e) {
            e.preventDefault(); exportReport("journal", "xlsx");
        });
        document.getElementById("btn-export-journal-pdf").addEventListener("click", function (e) {
            e.preventDefault(); exportReport("journal", "pdf");
        });
    });
})();
