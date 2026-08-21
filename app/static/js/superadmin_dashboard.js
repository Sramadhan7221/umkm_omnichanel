/**
 * Superadmin dashboard logic (Customer Request 1 Epic J).
 *
 * Talks to /api/superadmin/* routes (see app/routers/superadmin.py).
 */

(function () {
    "use strict";

    var API_BASE = "/api/superadmin";

    var MONTHS_ID = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];

    var monthlyChart = null;
    var monthlyRows = [];
    var pendingTable = null;
    var approvedTable = null;

    /** Escape a value for safe insertion into an HTML string (text content or quoted attribute). */
    function escapeHtml(value) {
        return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
        });
    }

    /** Render a (possibly very long) business name as a truncating, tooltip-bearing cell so it can't blow up the table layout. */
    function businessNameCell(name) {
        var safe = escapeHtml(name);
        return "<span class='d-inline-block text-truncate align-middle' style='max-width: 220px;' title='" + safe + "'>" + safe + "</span>";
    }

    var DATATABLE_LANGUAGE = {
        search: "Cari:",
        lengthMenu: "Tampilkan _MENU_ data",
        info: "Menampilkan _START_ - _END_ dari _TOTAL_ data",
        infoEmpty: "Tidak ada data",
        infoFiltered: "(disaring dari _MAX_ total data)",
        zeroRecords: "Data tidak ditemukan",
        paginate: { first: "Pertama", last: "Terakhir", next: "Berikutnya", previous: "Sebelumnya" },
    };

    /** All 12 months of the given year, e.g. monthKeysForYear(2026) -> ["2026-01", ..., "2026-12"] */
    function monthKeysForYear(year) {
        var keys = [];
        for (var m = 1; m <= 12; m++) {
            keys.push(year + "-" + String(m).padStart(2, "0"));
        }
        return keys;
    }

    /** Populate the year filter from the years present in `rows` plus the current year, capped at the current year. */
    function populateYearOptions(rows) {
        var currentYear = new Date().getFullYear();
        var years = {};
        years[currentYear] = true;
        rows.forEach(function (row) {
            var y = parseInt(row.month.split("-")[0], 10);
            if (y <= currentYear) years[y] = true;
        });
        var sorted = Object.keys(years).map(Number).sort(function (a, b) { return b - a; });

        var select = document.getElementById("monthly-owners-year");
        var prevValue = select.value;
        select.innerHTML = sorted.map(function (y) { return "<option value='" + y + "'>" + y + "</option>"; }).join("");
        select.value = sorted.indexOf(parseInt(prevValue, 10)) !== -1 ? prevValue : String(currentYear);
    }

    function renderMonthlyChart(year) {
        var container = document.getElementById("monthly-owners-chart");

        var countsByMonth = {};
        monthlyRows.forEach(function (row) { countsByMonth[row.month] = row.count; });

        var months = monthKeysForYear(year);
        var categories = months.map(function (month) { return MONTHS_ID[parseInt(month.split("-")[1], 10) - 1]; });
        var series = [{ name: "Registrasi Baru", data: months.map(function (month) { return countsByMonth[month] || 0; }) }];

        if (monthlyChart) {
            monthlyChart.updateOptions({ xaxis: { categories: categories } });
            monthlyChart.updateSeries(series);
        } else {
            container.innerHTML = "";
            monthlyChart = new ApexCharts(container, {
                chart: {
                    type: "bar",
                    height: 260,
                    toolbar: { show: false },
                    fontFamily: "inherit"
                },
                series: series,
                xaxis: { categories: categories },
                colors: ["#727cf5"],
                plotOptions: {
                    bar: { columnWidth: "45%", borderRadius: 4 }
                },
                dataLabels: { enabled: false },
                grid: { borderColor: "#f1f3fa" },
                tooltip: { y: { formatter: function (val) { return val + " registrasi"; } } }
            });
            monthlyChart.render();
        }
    }

    function loadStats() {
        return fetch(API_BASE + "/stats")
            .then(function (res) { return res.json(); })
            .then(function (data) {
                var activeOwnersEl = document.getElementById("stat-active-owners");
                if (activeOwnersEl) activeOwnersEl.textContent = data.active_owner_count;

                monthlyRows = data.monthly_new_owners;
                populateYearOptions(monthlyRows);
                renderMonthlyChart(parseInt(document.getElementById("monthly-owners-year").value, 10));
            });
    }

    function renderPending(owners) {
        var rows = owners.map(function (o) {
            var created = o.created_time ? o.created_time.substring(0, 10) : "-";
            var safeName = escapeHtml(o.business_name);
            return [
                businessNameCell(o.business_name),
                o.email,
                created,
                "<button class='btn btn-sm btn-success me-1 btn-approve' data-id='" + o.id + "' data-name='" + safeName + "'>Setujui</button>" +
                "<button class='btn btn-sm btn-outline-danger btn-reject' data-id='" + o.id + "' data-name='" + safeName + "'>Tolak</button>",
            ];
        });

        if (pendingTable) {
            pendingTable.clear();
            pendingTable.rows.add(rows);
            pendingTable.draw();
        } else {
            pendingTable = $("#pending-owners-datatable").DataTable({
                data: rows,
                columns: [
                    { title: "Bisnis" }, { title: "Email" }, { title: "Daftar" }, { title: "Aksi" },
                ],
                order: [[2, "asc"]],
                scrollX: true,
                scrollY: "360px",
                scrollCollapse: true,
                language: DATATABLE_LANGUAGE,
            });
        }
    }

    function loadPending() {
        return fetch(API_BASE + "/owners/pending")
            .then(function (res) { return res.json(); })
            .then(renderPending)
            .catch(function (err) { AppNotify.showErrorToast(err, "Gagal memuat daftar pendaftaran."); });
    }

    function renderApproved(owners) {
        var rows = owners.map(function (o) {
            var statusBadge = o.is_active
                ? "<span class='badge bg-success-subtle text-success'>Aktif</span>"
                : "<span class='badge bg-secondary-subtle text-secondary'>Nonaktif</span>";
            var safeName = escapeHtml(o.business_name);
            var actionBtn = o.is_active
                ? "<button class='btn btn-sm btn-outline-danger btn-deactivate' data-id='" + o.id + "' data-name='" + safeName + "'>Nonaktifkan</button>"
                : "<button class='btn btn-sm btn-outline-success btn-reactivate' data-id='" + o.id + "' data-name='" + safeName + "'>Aktifkan</button>";
            return [businessNameCell(o.business_name), o.email, statusBadge, actionBtn];
        });

        if (approvedTable) {
            approvedTable.clear();
            approvedTable.rows.add(rows);
            approvedTable.draw();
        } else {
            approvedTable = $("#approved-owners-datatable").DataTable({
                data: rows,
                columns: [
                    { title: "Bisnis" }, { title: "Email" }, { title: "Status" }, { title: "Aksi" },
                ],
                order: [[0, "asc"]],
                scrollX: true,
                scrollY: "360px",
                scrollCollapse: true,
                language: DATATABLE_LANGUAGE,
            });
        }
    }

    function loadApproved() {
        return fetch(API_BASE + "/owners/approved")
            .then(function (res) { return res.json(); })
            .then(renderApproved)
            .catch(function (err) { AppNotify.showErrorToast(err, "Gagal memuat daftar akun UMKM."); });
    }

    function decide(id, action, name) {
        var successMessage = action === "approve"
            ? "Pendaftaran " + (name || "owner") + " disetujui."
            : "Pendaftaran " + (name || "owner") + " ditolak.";

        function run() {
            return fetch(API_BASE + "/users/" + id + "/" + action, { method: "POST" })
                .then(function (res) {
                    if (!res.ok) {
                        return res.json().then(function (data) {
                            throw new Error(data.detail || "Gagal memproses");
                        });
                    }
                })
                .then(function () {
                    AppNotify.showSuccessToast(successMessage);
                    loadPending();
                    loadApproved();
                    loadStats();
                })
                .catch(function (err) { AppNotify.showErrorToast(err, "Gagal memproses permintaan."); });
        }

        if (action === "reject") {
            return AppNotify.confirmAction({
                title: "Tolak Pendaftaran",
                message: "Tolak pendaftaran " + (name || "owner ini") + "? Tindakan ini tidak dapat dibatalkan.",
                confirmText: "Ya, Tolak",
                variant: "danger",
            }).then(function (confirmed) { if (confirmed) return run(); });
        }
        return run();
    }

    function toggleActive(id, action, name) {
        var successMessage = action === "deactivate"
            ? "Akun " + (name || "owner") + " dinonaktifkan."
            : "Akun " + (name || "owner") + " diaktifkan kembali.";

        function run() {
            return fetch(API_BASE + "/users/" + id + "/" + action, { method: "POST" })
                .then(function (res) {
                    if (!res.ok) {
                        return res.json().then(function (data) {
                            throw new Error(data.detail || "Gagal memproses");
                        });
                    }
                })
                .then(function () {
                    AppNotify.showSuccessToast(successMessage);
                    loadApproved();
                    loadStats();
                })
                .catch(function (err) { AppNotify.showErrorToast(err, "Gagal memproses permintaan."); });
        }

        if (action === "deactivate") {
            return AppNotify.confirmAction({
                title: "Nonaktifkan Akun",
                message: "Nonaktifkan akun " + (name || "owner ini") + "? Owner tidak akan bisa masuk sampai diaktifkan kembali.",
                confirmText: "Ya, Nonaktifkan",
                variant: "danger",
            }).then(function (confirmed) { if (confirmed) return run(); });
        }
        return run();
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (window.lucide) lucide.createIcons();
        loadStats();
        loadPending();
        loadApproved();

        document.getElementById("pending-owners-datatable").addEventListener("click", function (e) {
            var approveBtn = e.target.closest(".btn-approve");
            var rejectBtn = e.target.closest(".btn-reject");
            if (approveBtn) decide(approveBtn.getAttribute("data-id"), "approve", approveBtn.getAttribute("data-name"));
            if (rejectBtn) decide(rejectBtn.getAttribute("data-id"), "reject", rejectBtn.getAttribute("data-name"));
        });

        document.getElementById("approved-owners-datatable").addEventListener("click", function (e) {
            var deactivateBtn = e.target.closest(".btn-deactivate");
            var reactivateBtn = e.target.closest(".btn-reactivate");
            if (deactivateBtn) toggleActive(deactivateBtn.getAttribute("data-id"), "deactivate", deactivateBtn.getAttribute("data-name"));
            if (reactivateBtn) toggleActive(reactivateBtn.getAttribute("data-id"), "reactivate", reactivateBtn.getAttribute("data-name"));
        });

        document.getElementById("monthly-owners-year").addEventListener("change", function (e) {
            renderMonthlyChart(parseInt(e.target.value, 10));
        });
    });
})();
