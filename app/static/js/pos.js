/**
 * Kasir POS page logic (Epic C).
 *
 * Talks to /api/inventory (existing, reused as-is) and /api/pos/* (see
 * app/routers/pos.py).
 */

(function () {
    "use strict";

    var products = {}; // sku -> {name, reference_price, stock_qty}
    var cart = []; // [{sku, name, qty, unit_price}]

    function formatRupiah(amount) {
        var n = Number(amount || 0);
        return "Rp " + n.toLocaleString("id-ID", { maximumFractionDigits: 0 });
    }

    function loadProducts() {
        return fetch("/api/inventory")
            .then(function (res) { return res.json(); })
            .then(function (items) {
                var select = document.getElementById("select-product");
                select.innerHTML = items.map(function (p) {
                    products[p.sku] = p;
                    return "<option value='" + p.sku + "'>" + p.name + " (stok " + p.stock_qty + ")</option>";
                }).join("");
                updateUnitPriceField();
            });
    }

    function loadPaymentMethods() {
        return fetch("/api/pos/payment-methods")
            .then(function (res) { return res.json(); })
            .then(function (rules) {
                var select = document.getElementById("select-payment");
                select.innerHTML = rules.map(function (r) {
                    return "<option value='" + r.no + "'>" + r.event_trigger + "</option>";
                }).join("");
            });
    }

    function updateUnitPriceField() {
        var sku = document.getElementById("select-product").value;
        var product = products[sku];
        document.getElementById("input-unit-price").value = product ? formatRupiah(product.reference_price) : "";
    }

    function renderCart() {
        var body = document.querySelector("#cart-table tbody");
        var total = 0;
        body.innerHTML = cart.length
            ? cart.map(function (line, idx) {
                var subtotal = line.qty * line.unit_price;
                total += subtotal;
                return "<tr><td>" + line.name + "</td><td class='text-end'>" + line.qty +
                    "</td><td class='text-end'>" + formatRupiah(line.unit_price) +
                    "</td><td class='text-end'>" + formatRupiah(subtotal) +
                    "</td><td class='text-end'><button class='btn btn-sm btn-outline-danger btn-remove-line' data-idx='" + idx + "'><i class='ri-delete-bin-line'></i></button></td></tr>";
            }).join("")
            : "<tr><td colspan='5' class='text-muted'>Belum ada barang.</td></tr>";
        document.getElementById("cart-total").textContent = formatRupiah(total);

        document.querySelectorAll(".btn-remove-line").forEach(function (btn) {
            btn.addEventListener("click", function () {
                cart.splice(parseInt(btn.getAttribute("data-idx"), 10), 1);
                renderCart();
            });
        });
    }

    function addItem() {
        var sku = document.getElementById("select-product").value;
        var qty = parseInt(document.getElementById("input-qty").value, 10);
        var product = products[sku];

        if (!product || isNaN(qty) || qty <= 0) {
            alert("Pilih barang dan qty yang valid.");
            return;
        }

        var alreadyInCart = cart.filter(function (l) { return l.sku === sku; }).reduce(function (sum, l) { return sum + l.qty; }, 0);
        if (alreadyInCart + qty > product.stock_qty) {
            alert("Stok '" + product.name + "' tidak cukup (tersedia " + product.stock_qty + ").");
            return;
        }

        var existing = cart.find(function (l) { return l.sku === sku; });
        if (existing) {
            existing.qty += qty;
        } else {
            cart.push({ sku: sku, name: product.name, qty: qty, unit_price: product.reference_price });
        }
        renderCart();
    }

    function resetCart() {
        cart = [];
        renderCart();
        document.getElementById("input-customer").value = "";
    }

    function saveNota() {
        var ruleNo = parseInt(document.getElementById("select-payment").value, 10);
        var customerRef = document.getElementById("input-customer").value.trim();

        if (!cart.length) {
            alert("Tambahkan minimal 1 barang ke nota.");
            return;
        }

        fetch("/api/pos/sales", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                rule_no: ruleNo, customer_ref: customerRef,
                items: cart.map(function (l) { return { sku: l.sku, qty: l.qty }; }),
            }),
        })
            .then(function (res) {
                if (!res.ok) return res.json().then(function (body) { throw new Error(body.detail || "Gagal menyimpan nota"); });
                return res.json();
            })
            .then(function (receipt) {
                renderReceipt(receipt);
                resetCart();
                loadProducts(); // refresh stock numbers after deduction
            })
            .catch(function (err) { alert(err.message); });
    }

    function renderReceipt(receipt) {
        document.getElementById("nota-toko-nama").textContent = receipt.nama_toko;
        document.getElementById("nota-no").textContent = receipt.no_nota;
        document.getElementById("nota-customer").textContent = receipt.nama_pelanggan;
        document.getElementById("nota-tanggal").textContent = receipt.tanggal;
        document.getElementById("nota-metode").textContent = receipt.metode_pembayaran;
        document.getElementById("nota-items").innerHTML = receipt.items.map(function (item, idx) {
            return "<tr><td>" + (idx + 1) + "</td><td>" + item.nama_barang + "</td><td class='text-end'>" + item.qty +
                "</td><td class='text-end'>" + formatRupiah(item.harga_satuan) +
                "</td><td class='text-end'>" + formatRupiah(item.total_harga) + "</td></tr>";
        }).join("");
        document.getElementById("nota-total").textContent = formatRupiah(receipt.total);

        document.getElementById("pos-form-area").classList.add("d-none");
        document.getElementById("nota-preview-row").classList.remove("d-none");
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (window.lucide) lucide.createIcons();

        loadProducts();
        loadPaymentMethods();
        renderCart();

        document.getElementById("select-product").addEventListener("change", updateUnitPriceField);
        document.getElementById("btn-add-item").addEventListener("click", addItem);
        document.getElementById("btn-save-nota").addEventListener("click", saveNota);
        document.getElementById("btn-print-nota").addEventListener("click", function () { window.print(); });
        document.getElementById("btn-new-sale").addEventListener("click", function () {
            document.getElementById("nota-preview-row").classList.add("d-none");
            document.getElementById("pos-form-area").classList.remove("d-none");
        });
    });
})();
