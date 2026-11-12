(() => {
    "use strict";

    const clientKey = "atmos_client_id";
    let clientId = localStorage.getItem(clientKey);
    if (!clientId) {
        clientId = `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
        localStorage.setItem(clientKey, clientId);
    }

    const iconPaths = {
        humidity: '<path d="M12 3s5.5 6.2 5.5 11a5.5 5.5 0 1 1-11 0C6.5 9.2 12 3 12 3Z"></path><path d="M9.5 14.2c.3 1.5 1.2 2.3 2.7 2.6"></path>',
        wind: '<path d="M3 8h10.5a2.5 2.5 0 1 0-2.2-3.7"></path><path d="M3 12h15a2 2 0 1 1-1.7 3"></path><path d="M3 16h7"></path>',
        sun: '<circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path>',
        pressure: '<circle cx="12" cy="12" r="8"></circle><path d="M12 8v4l2.5 2.5"></path><path d="M6.5 5.5A8 8 0 0 1 18 6"></path>',
        visibility: '<path d="M2.5 12S6 5.8 12 5.8 21.5 12 21.5 12 18 18.2 12 18.2 2.5 12 2.5 12Z"></path><circle cx="12" cy="12" r="2.7"></circle>',
        air: '<path d="M3 8h11M6 12h14M4 16h9"></path><circle cx="18.5" cy="8" r="1.5"></circle><circle cx="6.5" cy="16" r="1.5"></circle>',
        temperature: '<path d="M9 5a3 3 0 0 1 6 0v8.3a5 5 0 1 1-6 0Z"></path><path d="M12 8v8.5"></path>',
        umbrella: '<path d="M4 12a8 8 0 0 1 16 0H4Z"></path><path d="M12 12v6a2.5 2.5 0 0 0 5 0"></path><path d="M12 4v1"></path>',
        coat: '<path d="m8 4 4 2 4-2 3 4-2 2v10H7V10L5 8l3-4Z"></path><path d="M12 6v14M9 10h6"></path>',
        jacket: '<path d="m8 4 4 2 4-2 3 4-2 2v10H7V10L5 8l3-4Z"></path><path d="M12 6v14"></path>',
        water: '<path d="M12 3s6 6.7 6 11.2a6 6 0 1 1-12 0C6 9.7 12 3 12 3Z"></path>',
        drop: '<path d="M12 3s5 5.5 5 9.2a5 5 0 1 1-10 0C7 8.5 12 3 12 3Z"></path><path d="M9.5 12.8h5"></path>',
        mask: '<path d="M4 8.5c2.7-1 5.2-1 8 0 2.8-1 5.3-1 8 0v4c0 4.2-3.6 7.5-8 7.5S4 16.7 4 12.5v-4Z"></path><path d="M7.5 11.5c3-.7 6-.7 9 0M7.5 14c3 .7 6 .7 9 0"></path>',
        walk: '<circle cx="13" cy="4.5" r="2"></circle><path d="m11 9-3 4 3 1 2-3 3 3M10 21l1-5-3-2M14 11l2 4 3 1"></path>',
        layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"></path><path d="m3 12 9 5 9-5M3 16l9 5 9-5"></path>',
        sunscreen: '<circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.4 1.4M17.6 17.6 19 19M5 19l1.4-1.4M17.6 6.4 19 5"></path>',
        location: '<path d="M12 21s6-5.2 6-11a6 6 0 1 0-12 0c0 5.8 6 11 6 11Z"></path><circle cx="12" cy="10" r="2"></circle>',
        clock: '<circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3.2 2"></path>',
        arrow: '<path d="M5 12h14M13 6l6 6-6 6"></path>',
        refresh: '<path d="M20 11a8 8 0 1 0-2.2 5.5"></path><path d="M20 4v7h-7"></path>',
        info: '<circle cx="12" cy="12" r="9"></circle><path d="M12 11v6M12 7.5v.1"></path>',
    };

    function icon(name, className = "") {
        const path = iconPaths[name] || iconPaths.info;
        return `<svg class="inline-icon ${className}" viewBox="0 0 24 24" aria-hidden="true">${path}</svg>`;
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    async function apiFetch(url, options = {}) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), options.timeout || 28000);
        const externalSignal = options.signal;
        if (externalSignal) {
            if (externalSignal.aborted) controller.abort();
            else externalSignal.addEventListener("abort", () => controller.abort(), { once: true });
        }
        try {
            const response = await fetch(url, {
                ...options,
                signal: controller.signal,
                headers: {
                    "X-Client-ID": clientId,
                    "Accept": "application/json",
                    ...(options.headers || {}),
                },
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                const apiError = new Error(data?.error?.message || `请求失败（${response.status}）`);
                apiError.code = data?.error?.code || "HTTP_ERROR";
                apiError.details = data?.error?.details;
                apiError.status = response.status;
                apiError.requestId = data?.request_id;
                throw apiError;
            }
            return data;
        } catch (error) {
            if (error.name === "AbortError") {
                const timeoutError = new Error("请求时间有点久，请稍后重试");
                timeoutError.code = "TIMEOUT";
                throw timeoutError;
            }
            throw error;
        } finally {
            clearTimeout(timeout);
        }
    }

    function debounce(callback, wait = 180) {
        let timer;
        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => callback(...args), wait);
        };
    }

    class Autocomplete {
        constructor(root, input, { onSelect, enterSelectsFirst = true } = {}) {
            this.root = root;
            this.input = input;
            this.list = root.querySelector(".suggestion-list");
            this.onSelect = onSelect;
            this.enterSelectsFirst = enterSelectsFirst;
            this.items = [];
            this.activeIndex = -1;
            this.sequence = 0;
            this.abortController = null;
            if (!this.input || !this.list) return;

            const search = debounce(() => this.search(this.input.value), 160);
            this.input.addEventListener("input", () => {
                this.activeIndex = -1;
                search();
            });
            this.input.addEventListener("focus", () => {
                if (this.input.value.trim()) this.search(this.input.value);
            });
            this.input.addEventListener("keydown", (event) => this.onKeyDown(event));
            this.list.addEventListener("mousedown", (event) => event.preventDefault());
            this.list.addEventListener("click", (event) => {
                const item = event.target.closest("[data-index]");
                if (!item) return;
                this.choose(Number(item.dataset.index));
            });
            document.addEventListener("click", (event) => {
                if (!this.root.contains(event.target)) this.close();
            });
        }

        async search(query) {
            const value = query.trim();
            if (!value) {
                this.close();
                return;
            }
            const sequence = ++this.sequence;
            this.abortController?.abort();
            this.abortController = new AbortController();
            this.list.hidden = false;
            this.list.innerHTML = `
                <div class="suggestion-state">
                    <span class="mini-spinner"></span> 正在寻找这座城市的天气…
                </div>`;
            try {
                const data = await apiFetch(`/api/cities?query=${encodeURIComponent(value)}`, {
                    signal: this.abortController.signal,
                    timeout: 8000,
                });
                if (sequence !== this.sequence) return;
                this.items = data.suggestions || [];
                this.render();
            } catch (error) {
                if (error.name !== "AbortError" && sequence === this.sequence) {
                    this.list.innerHTML = `
                        <div class="suggestion-state error-text">联想暂时不可用，仍可直接按回车查询</div>`;
                }
            }
        }

        render() {
            if (!this.items.length) {
                this.list.innerHTML = `
                    <div class="suggestion-empty">
                        <strong>没有匹配的城市</strong>
                        <span>试试“北京市”、拼音，或检查输入是否有误</span>
                    </div>`;
                return;
            }
            this.list.innerHTML = this.items.map((item, index) => `
                <button class="suggestion-item ${index === this.activeIndex ? "active" : ""}"
                    type="button" role="option" aria-selected="${index === this.activeIndex}" data-index="${index}">
                    <span class="suggestion-pin">${icon("location")}</span>
                    <span class="suggestion-name">${escapeHtml(item.name)}</span>
                    <span class="suggestion-note">${item.matched === "fuzzy" ? "你可能想去" : "城市天气"}</span>
                    ${icon("arrow", "suggestion-arrow")}
                </button>
            `).join("");
        }

        choose(index) {
            const selected = this.items[index];
            if (!selected) return;
            this.input.value = selected.name;
            this.close();
            this.onSelect?.(selected);
        }

        onKeyDown(event) {
            if (this.list.hidden) return;
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                const direction = event.key === "ArrowDown" ? 1 : -1;
                this.activeIndex = (this.activeIndex + direction + this.items.length) % this.items.length;
                this.render();
                this.list.querySelector(".suggestion-item.active")?.scrollIntoView({ block: "nearest" });
            } else if (event.key === "Enter" && this.activeIndex >= 0) {
                event.preventDefault();
                this.choose(this.activeIndex);
            } else if (event.key === "Escape") {
                this.close();
            }
        }

        close() {
            this.abortController?.abort();
            this.list.hidden = true;
            this.activeIndex = -1;
        }
    }

    function showToast(message, tone = "info", duration = 3600) {
        const toast = document.getElementById("toast");
        if (!toast) return;
        toast.textContent = message;
        toast.dataset.tone = tone;
        toast.classList.add("visible");
        clearTimeout(showToast.timer);
        showToast.timer = setTimeout(() => toast.classList.remove("visible"), duration);
    }

    function navigateToWeather(city) {
        if (!city?.trim()) {
            showToast("请输入城市名称", "warning");
            return;
        }
        const selected = city.trim();
        const recent = JSON.parse(localStorage.getItem("atmos_recent_cities") || "[]");
        const nextRecent = [selected, ...recent.filter((item) => item !== selected)].slice(0, 5);
        localStorage.setItem("atmos_recent_cities", JSON.stringify(nextRecent));
        window.location.href = `/weather.html?city=${encodeURIComponent(selected)}`;
    }

    async function locateCity(onLocated) {
        if (!navigator.geolocation) {
            showToast("当前浏览器不支持定位，请手动搜索城市", "warning");
            return;
        }
        const buttons = document.querySelectorAll(".location-button, .location-header");
        buttons.forEach((button) => {
            button.classList.add("is-loading");
            button.setAttribute("aria-busy", "true");
        });
        showToast("正在获取你的位置…", "info");

        navigator.geolocation.getCurrentPosition(
            async (position) => {
                try {
                    const { latitude, longitude } = position.coords;
                    const data = await apiFetch(`/api/location?lat=${latitude}&lon=${longitude}`, {
                        timeout: 15000,
                    });
                    showToast(data.message || "定位成功", "success");
                    if (onLocated) {
                        onLocated(data.city);
                    } else {
                        navigateToWeather(data.city.name);
                    }
                } catch (error) {
                    showToast(error.message || "定位完成，但城市匹配失败", "warning");
                } finally {
                    buttons.forEach((button) => {
                        button.classList.remove("is-loading");
                        button.removeAttribute("aria-busy");
                    });
                }
            },
            (error) => {
                const messages = {
                    1: "定位权限未开启，请在浏览器设置中允许定位",
                    2: "暂时无法获取位置，请手动搜索城市",
                    3: "定位等待超时，请稍后重试",
                };
                showToast(messages[error.code] || "定位失败，请手动搜索", "warning");
                buttons.forEach((button) => {
                    button.classList.remove("is-loading");
                    button.removeAttribute("aria-busy");
                });
            },
            { enableHighAccuracy: false, timeout: 12000, maximumAge: 10 * 60 * 1000 },
        );
    }

    function formatClock(isoValue) {
        if (!isoValue) return "--:--";
        const date = new Date(isoValue);
        if (Number.isNaN(date.getTime())) return "--:--";
        return new Intl.DateTimeFormat("zh-CN", {
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
        }).format(date);
    }

    function formatFullDate(date = new Date()) {
        return new Intl.DateTimeFormat("zh-CN", {
            month: "long",
            day: "numeric",
            weekday: "long",
        }).format(date);
    }

    window.Atmos = {
        apiFetch,
        Autocomplete,
        debounce,
        escapeHtml,
        formatClock,
        formatFullDate,
        icon,
        locateCity,
        navigateToWeather,
        showToast,
        clientId,
    };
})();
