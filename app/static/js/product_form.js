/**
 * Tambah / Edit Produk form logic (Fase 6).
 *
 * Same page template handles both modes: window.PRODUCT_FORM_SKU is empty
 * string for "create", or the SKU being edited. In edit mode the form is
 * pre-filled via GET /api/inventory/products/{sku}/detail, and submits go
 * to PUT instead of POST.
 */

(function () {
    "use strict";

    var EDIT_SKU = window.PRODUCT_FORM_SKU || "";
    var IS_EDIT = EDIT_SKU !== "";
    var platformsCache = [];
    var existingImages = [];
    var removedImageIds = [];

    function showError(message) {
        var el = document.getElementById("form-error");
        el.textContent = message;
        el.classList.remove("d-none");
        window.scrollTo(0, 0);
    }

    function formatRupiah(amount) {
        var n = Number(amount || 0);
        return "Rp " + n.toLocaleString("id-ID", { maximumFractionDigits: 0 });
    }

    function renderPlatformCheckboxes(platforms, checkedChannels) {
        checkedChannels = checkedChannels || [];

        // Hanya platform yang aktif (menu Platform) yang bisa dipilih di sini —
        // platform nonaktif tidak boleh kebagian produk baru.
        var activePlatforms = platforms.filter(function (p) { return p.is_active; });

        var container = document.getElementById("platform-checkboxes");
        container.innerHTML = activePlatforms.map(function (p) {
            var checked = checkedChannels.indexOf(p.name) !== -1 ? "checked" : "";
            var id = "platform-cb-" + p.code;
            return (
                '<div class="d-flex align-items-center justify-content-between border rounded p-2 mb-2">' +
                '<div class="form-check">' +
                '<input class="form-check-input platform-cb" type="checkbox" id="' + id + '" value="' + p.name + '" ' + checked + ' />' +
                '<label class="form-check-label" for="' + id + '">' + p.name + '</label>' +
                '</div>' +
                '<span class="badge bg-light text-dark">Fee ' + p.fee_rate + '%</span>' +
                '</div>'
            );
        }).join("");

        if (activePlatforms.length === 0) {
            container.innerHTML = '<p class="text-muted mb-0">Belum ada platform aktif. Aktifkan platform dulu di menu <a href="/platforms">Platform</a>.</p>';
        }

        // Kalau produk (mode edit) sudah terhubung ke platform yang sekarang
        // nonaktif, tampilkan sebagai info saja (bukan checkbox) supaya
        // mapping itu tidak terasa "hilang begitu saja" dari sudut pandang
        // pengguna — checkbox di sini memang tidak mengubah mapping platform
        // (lihat catatan di update_product), jadi ini murni informasi.
        var inactiveButMapped = platforms.filter(function (p) {
            return !p.is_active && checkedChannels.indexOf(p.name) !== -1;
        });
        var noteEl = document.getElementById("platform-inactive-note");
        if (inactiveButMapped.length > 0) {
            noteEl.classList.remove("d-none");
            noteEl.textContent = "Produk ini juga tercatat di platform nonaktif: " +
                inactiveButMapped.map(function (p) { return p.name; }).join(", ") +
                ". Aktifkan kembali platform tersebut di menu Platform kalau perlu.";
        } else {
            noteEl.classList.add("d-none");
        }
    }

    function loadPlatforms(checkedChannels) {
        return fetch("/api/platforms")
            .then(function (res) { return res.json(); })
            .then(function (platforms) {
                platformsCache = platforms;
                renderPlatformCheckboxes(platforms, checkedChannels || []);
            });
    }

    function renderExistingImages() {
        var section = document.getElementById("existing-images-section");
        var container = document.getElementById("existing-images");
        var visible = existingImages.filter(function (img) {
            return removedImageIds.indexOf(img.id) === -1;
        });

        if (visible.length === 0) {
            section.classList.add("d-none");
            return;
        }
        section.classList.remove("d-none");
        container.innerHTML = visible.map(function (img) {
            return (
                '<span class="photo-thumb-wrap">' +
                '<img src="' + img.url + '" class="photo-thumb" alt="foto produk">' +
                (img.is_primary ? '<span class="badge bg-primary" style="position:absolute;bottom:2px;left:2px;font-size:9px;">Utama</span>' : '') +
                '<button type="button" class="btn btn-danger photo-thumb-remove" data-image-id="' + img.id + '">&times;</button>' +
                '</span>'
            );
        }).join("");
    }

    function previewFiles(inputEl, containerEl) {
        containerEl.innerHTML = "";
        var files = inputEl.files;
        for (var i = 0; i < files.length; i++) {
            var reader = new FileReader();
            reader.onload = (function (file) {
                return function (e) {
                    var img = document.createElement("img");
                    img.src = e.target.result;
                    img.className = "photo-thumb";
                    img.style.margin = "4px";
                    containerEl.appendChild(img);
                };
            })(files[i]);
            reader.readAsDataURL(files[i]);
        }
    }

    function loadExistingProduct() {
        return fetch("/api/inventory/products/" + encodeURIComponent(EDIT_SKU) + "/detail")
            .then(function (res) {
                if (!res.ok) throw new Error("Produk tidak ditemukan");
                return res.json();
            })
            .then(function (p) {
                document.getElementById("f-sku").value = p.sku;
                document.getElementById("f-name").value = p.name;
                document.getElementById("f-description").value = p.description || "";
                document.getElementById("f-stock").value = p.stock_qty;
                document.getElementById("f-price").value = p.reference_price;
                document.getElementById("f-ppn").value = p.ppn_rate;

                existingImages = p.images || [];
                renderExistingImages();

                var checkedChannels = p.mappings.map(function (m) { return m.channel; });
                return loadPlatforms(checkedChannels);
            });
    }

    function buildFormData() {
        var formData = new FormData();
        formData.append("name", document.getElementById("f-name").value.trim());
        formData.append("description", document.getElementById("f-description").value.trim());
        formData.append("stock_qty", document.getElementById("f-stock").value || "0");
        formData.append("reference_price", document.getElementById("f-price").value || "0");
        formData.append("ppn_rate", document.getElementById("f-ppn").value || "11");

        var primaryFile = document.getElementById("f-primary-image").files[0];
        if (primaryFile) {
            formData.append(IS_EDIT ? "new_primary_image" : "primary_image", primaryFile);
        }

        var galleryFiles = document.getElementById("f-gallery-images").files;
        for (var i = 0; i < galleryFiles.length; i++) {
            formData.append(IS_EDIT ? "new_gallery_images" : "gallery_images", galleryFiles[i]);
        }

        if (!IS_EDIT) {
            var sku = document.getElementById("f-sku").value.trim();
            formData.append("sku", sku);
            document.querySelectorAll(".platform-cb:checked").forEach(function (cb) {
                formData.append("channels", cb.value);
            });
        } else {
            formData.append("remove_image_ids", JSON.stringify(removedImageIds));
            formData.append("note", document.getElementById("f-note").value.trim());
        }

        return formData;
    }

    function submitForm() {
        var btn = document.getElementById("btn-save-product");
        btn.disabled = true;

        var formData = buildFormData();

        if (!IS_EDIT && !formData.get("sku")) {
            showError("SKU wajib diisi.");
            btn.disabled = false;
            return;
        }
        if (!document.getElementById("f-name").value.trim()) {
            showError("Nama produk wajib diisi.");
            btn.disabled = false;
            return;
        }

        var url = IS_EDIT
            ? "/api/inventory/products/" + encodeURIComponent(EDIT_SKU)
            : "/api/inventory/products";
        var method = IS_EDIT ? "PUT" : "POST";

        fetch(url, { method: method, body: formData })
            .then(function (res) {
                if (!res.ok) {
                    return res.json().then(function (data) {
                        throw new Error(data.detail || "Gagal menyimpan produk");
                    });
                }
                return res.json();
            })
            .then(function (data) {
                window.location.href = "/inventory/" + encodeURIComponent(data.sku || EDIT_SKU);
            })
            .catch(function (err) {
                showError(err.message);
                btn.disabled = false;
            });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (window.lucide) lucide.createIcons();

        if (IS_EDIT) {
            document.getElementById("note-card").style.display = "";
            loadExistingProduct().catch(function (err) { showError(err.message); });
        } else {
            loadPlatforms([]);
        }

        document.getElementById("f-primary-image").addEventListener("change", function () {
            previewFiles(this, document.getElementById("primary-preview"));
        });
        document.getElementById("f-gallery-images").addEventListener("change", function () {
            previewFiles(this, document.getElementById("gallery-preview"));
        });

        document.getElementById("existing-images").addEventListener("click", function (e) {
            var btn = e.target.closest(".photo-thumb-remove");
            if (!btn) return;
            var id = parseInt(btn.getAttribute("data-image-id"), 10);
            removedImageIds.push(id);
            renderExistingImages();
        });

        document.getElementById("btn-save-product").addEventListener("click", submitForm);
    });
})();
