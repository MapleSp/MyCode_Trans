(() => {
    "use strict";

    const { Autocomplete, escapeHtml, icon, locateCity, navigateToWeather, showToast } = window.Atmos;
    const form = document.getElementById("city-search-form");
    const input = document.getElementById("city-search");
    const submitButton = form?.querySelector(".submit-button");

    function setSearching(isSearching) {
        if (!submitButton) return;
        submitButton.classList.toggle("is-loading", isSearching);
        submitButton.disabled = isSearching;
        submitButton.querySelector(".button-label").textContent = isSearching ? "定位天气中" : "开始观测";
    }

    if (form && input) {
        new Autocomplete(input.closest("[data-autocomplete]"), input, {
            onSelect: (city) => navigateToWeather(city.name),
        });

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            const city = input.value.trim();
            if (!city) {
                input.focus();
                showToast("先输入一个城市名称", "warning");
                return;
            }
            setSearching(true);
            navigateToWeather(city);
        });
    }

    document.querySelectorAll("[data-city]").forEach((button) => {
        button.addEventListener("click", () => navigateToWeather(button.dataset.city));
    });

    document.getElementById("location-button")?.addEventListener("click", () => locateCity());

    function updateClock() {
        const node = document.getElementById("panel-clock");
        if (!node) return;
        node.textContent = new Intl.DateTimeFormat("zh-CN", {
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
        }).format(new Date());
    }

    function renderRecent() {
        const recent = JSON.parse(localStorage.getItem("atmos_recent_cities") || "[]");
        const wrapper = document.getElementById("recent-searches");
        const list = document.getElementById("recent-list");
        if (!wrapper || !list || !recent.length) return;
        wrapper.hidden = false;
        list.innerHTML = recent.slice(0, 4).map((city) => `
            <button type="button" data-recent-city="${escapeHtml(city)}">
                <span>${icon("clock")}</span>
                ${escapeHtml(city)}
                ${icon("arrow")}
            </button>
        `).join("");
        list.querySelectorAll("[data-recent-city]").forEach((button) => {
            button.addEventListener("click", () => navigateToWeather(button.dataset.recentCity));
        });
    }

    document.getElementById("clear-recent")?.addEventListener("click", () => {
        localStorage.removeItem("atmos_recent_cities");
        document.getElementById("recent-searches").hidden = true;
        showToast("最近记录已清除", "success");
    });

    updateClock();
    setInterval(updateClock, 30_000);
    renderRecent();
})();
