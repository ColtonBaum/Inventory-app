// inventory_app/static/js/inventory.js
// Supports legacy templates (inventory.html) that don't use inline scripts.

document.addEventListener('DOMContentLoaded', function () {

    // ----- Accordion toggles -----
    document.querySelectorAll('.accordion h3').forEach(function (header) {
        header.addEventListener('click', function () {
            var body = header.nextElementSibling;
            if (!body) return;
            var isOpen = body.classList.contains('open');
            body.classList.toggle('open', !isOpen);
            body.style.display = isOpen ? 'none' : 'block';
        });
    });

    // ----- Show/hide note fields based on checkbox state -----
    document.querySelectorAll('.inv-item, .item-block').forEach(function (block) {
        var missing = block.querySelector('input[name$="_status_missing"], input[name$="_missing"]');
        var redtag  = block.querySelector('input[name$="_status_redtag"],  input[name$="_redtag"]');
        var noteMissing = block.querySelector('.note-missing');
        var noteRedtag  = block.querySelector('.note-redtag');

        function sync() {
            if (noteMissing) noteMissing.classList.toggle('visible', !!(missing && missing.checked));
            if (noteRedtag)  noteRedtag.classList.toggle('visible',  !!(redtag  && redtag.checked));
        }

        if (missing) missing.addEventListener('change', sync);
        if (redtag)  redtag.addEventListener('change', sync);
        sync();
    });

    // ----- Expand / Collapse All -----
    var expandBtn   = document.getElementById('expandAll');
    var collapseBtn = document.getElementById('collapseAll');

    function setAll(open) {
        document.querySelectorAll('.acc-item').forEach(function (item) {
            item.classList.toggle('open', open);
            var h = item.querySelector('.acc-header');
            if (h) h.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
    }

    if (expandBtn)   expandBtn.addEventListener('click',   function () { setAll(true);  });
    if (collapseBtn) collapseBtn.addEventListener('click', function () { setAll(false); });

});
