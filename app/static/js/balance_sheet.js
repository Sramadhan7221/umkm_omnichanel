/**
 * Neraca page logic (Epic F).
 *
 * Talks to /api/financial/balance-sheet (see app/routers/financial.py).
 */

(function () {
    "use strict";

    function formatRupiah(amount) {
        var n = Number(amount || 0);
        return "Rp " + n.toLocaleString("id-ID", { maximumFractionDigits: 0 });
    }

    function todayISO() {
        return new Date().toISOString().slice(0, 10);
    }

    function renderSection(tableId, totalId, rows) {
        var body = document.querySelector("#" + tableId + " tbody");
        body.innerHTML = rows.length
            ? rows.map(function (r) {
                return "<tr><td>" + (r.kode_akun || "-") + "</td><td>" + r.nama_akun +
                    (r.is_computed ? " <span class='badge bg-info-subtle text-info'>dihitung</span>" : "") +
                    "</td><td class='text-end'>" + formatRupiah(r.saldo) + "</td></tr>";
            }).join("")
            : "<tr><td colspan='3' class='text-muted'>Tidak ada akun.</td></tr>";
    }

    function renderKasOutletBreakdown(asetRows) {
        var kasRow = asetRows.find(function (r) { return r.kode_akun === "1111"; });
        var container = document.getElementById("kas-outlet-breakdown");
        if (!kasRow || !kasRow.breakdown_outlet || !kasRow.breakdown_outlet.length) {
            container.innerHTML = "";
            return;
        }
        container.innerHTML = "<p class='text-muted mb-1'>Rincian 1111 Kas di Tangan per outlet:</p>" +
            "<table class='table table-sm mb-0'><tbody>" +
            kasRow.breakdown_outlet.map(function (b) {
                return "<tr><td>" + b.nama_outlet + "</td><td class='text-end'>" + formatRupiah(b.saldo) + "</td></tr>";
            }).join("") +
            "</tbody></table>";
    }

    function loadBalanceSheet() {
        var asOf = document.getElementById("as-of-date").value || todayISO();
        return fetch("/api/financial/balance-sheet?as_of=" + asOf)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                renderSection("aset-table", "total-aset", data.aset);
                renderSection("kewajiban-table", "total-kewajiban", data.kewajiban);
                renderSection("ekuitas-table", "total-ekuitas", data.ekuitas);
                renderKasOutletBreakdown(data.aset);

                document.getElementById("total-aset").textContent = formatRupiah(data.total_aset);
                document.getElementById("total-kewajiban").textContent = formatRupiah(data.total_kewajiban);
                document.getElementById("total-ekuitas").textContent = formatRupiah(data.total_ekuitas);

                var banner = document.getElementById("balance-check-banner");
                var text = document.getElementById("balance-check-text");
                if (data.is_balanced) {
                    banner.className = "alert alert-success";
                    text.textContent = "Neraca balance: Aset (" + formatRupiah(data.total_aset) +
                        ") = Kewajiban + Ekuitas (" + formatRupiah(data.total_kewajiban_ekuitas) + ")";
                } else {
                    banner.className = "alert alert-danger";
                    text.textContent = "Neraca TIDAK balance: Aset (" + formatRupiah(data.total_aset) +
                        ") vs Kewajiban + Ekuitas (" + formatRupiah(data.total_kewajiban_ekuitas) + ")";
                }
            });
    }

    function exportBalanceSheet(format) {
        var asOf = document.getElementById("as-of-date").value || todayISO();
        window.location.href = "/api/financial/balance-sheet/export?as_of=" + asOf + "&format=" + format;
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (window.lucide) lucide.createIcons();
        document.getElementById("as-of-date").value = todayISO();

        loadBalanceSheet();

        document.getElementById("as-of-date").addEventListener("change", loadBalanceSheet);
        document.getElementById("btn-export-bs-xlsx").addEventListener("click", function (e) {
            e.preventDefault(); exportBalanceSheet("xlsx");
        });
        document.getElementById("btn-export-bs-pdf").addEventListener("click", function (e) {
            e.preventDefault(); exportBalanceSheet("pdf");
        });
    });
})();
