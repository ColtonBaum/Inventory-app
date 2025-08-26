// inventory_app/static/js/inventory.js
document.addEventListener("DOMContentLoaded", function () {
    // Accordion toggles
    document.querySelectorAll(".accordion h3").forEach(header => {
        header.addEventListener("click", () => {
            const body = header.nextElementSibling;
            body.style.display = (body.style.display === "block") ? "none" : "block";
        });
    });

    // Conditional inputs for inventory + extra tooling items
    document.querySelectorAll(".item-block").forEach(block => {
        const itemId = block.dataset.item;
        const radios = block.querySelectorAll(`input[name="${itemId}_status"]`);
        const condInputs = block.querySelector(".conditional-inputs");

        radios.forEach(radio => {
            radio.addEventListener("change", () => {
                if (
                    radio.value === "Missing" ||
                    radio.value === "Red Tag" ||
                    radio.value === "Not Returned"
                ) {
                    condInputs.classList.remove("hidden");
                } else {
                    condInputs.classList.add("hidden");
                }
            });
        });
    });
});
