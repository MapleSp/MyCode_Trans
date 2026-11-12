(() => {
    "use strict";

    const {
        Autocomplete,
        apiFetch,
        escapeHtml,
        formatClock,
        formatFullDate,
        icon,
        locateCity,
        navigateToWeather,
        showToast,
    } = window.Atmos;

    const elements = {
        loading: document.getElementById("loading-state"),
        error: document.getElementById("error-state"),
        content: document.getElementById("weather-content"),
        errorTitle: document.getElementById("error-title"),
        errorMessage: document.getElementById("error-message"),
        errorSuggestions: document.getElementById("error-suggestions"),
    };

    let currentPayload = null;
    let currentCityName = "";

    function queryCity() {
        return new URLSearchParams(window.location.search).get("city")?.trim() || "";
    }

    function showLoading() {
        elements.loading.hidden = false;
        elements.error.hidden = true;
        elements.content.hidden = true;
    }

    function showError(error, city) {
        elements.loading.hidden = true;
        elements.content.hidden = true;
        elements.error.hidden = false;
        const notFound = error.code === "CITY_NOT_FOUND";
        elements.errorTitle.textContent = notFound ? `没有找到“${city}”` : "天气暂时被云层遮住";
        elements.errorMessage.textContent = notFound
            ? "可能是城市名称有误。根据你的输入，我们找到了这些地方："
            : error.message || "获取天气时遇到一点问题，请稍后重试。";
        const suggestions = error.details?.suggestions || [];
        elements.errorSuggestions.innerHTML = suggestions.map((item) => `
            <button type="button" data-suggestion="${escapeHtml(item.name)}">
                ${icon("location")} ${escapeHtml(item.name)} ${icon("arrow")}
            </button>
        `).join("");
        elements.errorSuggestions.querySelectorAll("[data-suggestion]").forEach((button) => {
            button.addEventListener("click", () => navigateToWeather(button.dataset.suggestion));
        });

        if (!notFound) {
            const retry = document.createElement("button");
            retry.className = "retry-button";
            retry.type = "button";
            retry.innerHTML = `${icon("refresh")} 重新读取天气`;
            retry.addEventListener("click", () => loadWeather(city));
            elements.errorSuggestions.prepend(retry);
        }
    }

    async function loadWeather(city) {
        if (!city) {
            showError({ code: "CITY_REQUIRED", message: "请选择一个城市" }, "空白的城市");
            return;
        }
        currentCityName = city;
        showLoading();
        window.scrollTo({ top: 0, behavior: "smooth" });
        try {
            const payload = await apiFetch(`/api/weather/${encodeURIComponent(city)}`);
            currentPayload = payload;
            renderWeather(payload);
            showToast(`已更新 ${payload.city.name} 的天气`, "success", 2200);
        } catch (error) {
            console.error("天气加载失败：", error);
            showError(error, city);
        }
    }

    function setText(id, value) {
        const node = document.getElementById(id);
        if (node) node.textContent = value;
    }

    function number(value, fallback = "--") {
        return value === null || value === undefined || Number.isNaN(Number(value))
            ? fallback
            : Math.round(Number(value));
    }

    function renderWeather(payload) {
        const current = payload.current || {};
        const advice = payload.advice || {};
        const forecast = payload.forecast || [];
        const meta = payload.meta || {};
        const cityName = payload.city?.name || currentCityName;
        currentCityName = cityName;

        window.document.title = `${cityName} · 天气观测 | Atmos`;
        setText("hero-city", cityName);
        setText("hero-date", formatFullDate());
        setText("current-temperature", number(current.temperature));
        setText("current-weather", current.weather || "天气信息暂缺");
        setText("feels-like", `${number(current.feels_like)}°`);
        setText(
            "today-range",
            `${number(current.temperature_low)}° / ${number(current.temperature_high)}°`,
        );
        setText("hero-humidity", `${number(current.humidity)}%`);
        setText(
            "hero-wind",
            `${current.wind_direction || "暂无"} ${current.wind_level || ""}`.trim(),
        );
        setText(
            "hero-air",
            current.air_quality?.level
                ? `${current.air_quality.level} ${number(current.air_quality.score)}`
                : "暂无",
        );
        setText("updated-time", formatClock(meta.updated_at || meta.fetched_at));
        setText("advice-headline", advice.headline || "天气平稳，出门前再看一眼天空");
        setText("advice-summary", advice.summary || "暂无分析数据。");
        setText("outfit-advice", advice.outfit || "根据体感及时增减衣物。");
        setText("activity-advice", advice.activity || "关注天气变化，合理安排活动。");
        setText("best-window", advice.best_window || "出门前关注临近预报。");
        setText("comfort-score", number(advice.comfort_score, 70));
        setText("risk-level", advice.risk_level || "平稳");
        setText("trend-label", advice.trend || "未来趋势分析");
        setText("recommendation-count", `${advice.recommendations?.length || 0} 条建议`);
        setText(
            "data-quality",
            `数据完整度 ${number(payload.data_quality?.score, 0)}% · ${payload.data_quality?.label || "未知"}`,
        );

        const weatherArt = document.getElementById("weather-art");
        weatherArt.dataset.weather = normalizeWeatherKind(current.icon || current.weather);
        document.body.dataset.weather = weatherArt.dataset.weather;
        document.getElementById("weather-hero").dataset.weather = weatherArt.dataset.weather;

        document.getElementById("hero-tags").innerHTML = [
            `<span>${escapeHtml(advice.weather_mood || "天气观察中")}</span>`,
            current.rainfall_mm ? `<span>降水 ${number(current.rainfall_mm, 0)} mm</span>` : "",
        ].filter(Boolean).join("");

        renderSource(meta);
        renderBanner(meta);
        renderAlerts(payload.alerts || []);
        renderFactors(advice.factors || []);
        renderMetrics(current, payload.indices || []);
        renderForecast(forecast);
        renderTrendChart(forecast);
        renderRecommendations(advice.recommendations || []);
        renderIndices(payload.indices || []);

        const ring = document.getElementById("score-ring");
        ring.style.setProperty("--score", Math.max(0, Math.min(100, Number(advice.comfort_score) || 0)));

        elements.loading.hidden = true;
        elements.error.hidden = true;
        elements.content.hidden = false;
    }

    function renderSource(meta) {
        const badge = document.getElementById("source-badge");
        const label = document.getElementById("source-label");
        badge.classList.remove("is-demo", "is-stale", "is-cache");
        if (meta.mode === "demo") {
            badge.classList.add("is-demo");
            label.textContent = "演示数据";
        } else if (meta.is_stale) {
            badge.classList.add("is-stale");
            label.textContent = "历史快照";
        } else if (["memory", "sqlite"].includes(meta.cache_layer)) {
            badge.classList.add("is-cache");
            label.textContent = meta.cache_layer === "memory" ? "智能缓存" : "持久化缓存";
        } else {
            label.textContent = "实时数据";
        }
        badge.title = `${meta.source || "天气数据"} · 缓存层：${meta.cache_layer || "live"}`;
        setText("hero-kicker", meta.mode === "live" ? "LIVE WEATHER INTELLIGENCE" : "WEATHER INTELLIGENCE");
    }

    function renderBanner(meta) {
        const banner = document.getElementById("status-banner");
        const messages = [];
        if (meta.mode === "demo") {
            messages.push(`在线天气与历史快照均暂不可用，当前为演示数据。${meta.reason || ""}`);
        } else if (meta.is_stale) {
            messages.push("实时天气暂时不可用，已展示最近一次保存的观测快照。");
        }
        if (messages.length) {
            banner.hidden = false;
            banner.innerHTML = `${icon("info")}<span>${escapeHtml(messages.join(" "))}</span>`;
        } else {
            banner.hidden = true;
        }
    }

    function renderAlerts(alerts) {
        const wrapper = document.getElementById("official-alerts");
        if (!alerts.length) {
            wrapper.hidden = true;
            return;
        }
        wrapper.hidden = false;
        wrapper.innerHTML = alerts.map((alert) => `
            <div class="official-alert">
                ${icon("info")}
                <div>
                    <strong>${escapeHtml(alert.title)}</strong>
                    <span>${escapeHtml(alert.level)} ${escapeHtml(alert.description || "")}</span>
                </div>
            </div>
        `).join("");
    }

    function renderFactors(factors) {
        const wrapper = document.getElementById("factor-chips");
        wrapper.innerHTML = factors.slice(0, 4).map((factor) => `
            <span class="factor-chip">
                <i></i>${escapeHtml(factor.title)}
            </span>
        `).join("");
    }

    function metricCard({ iconName, label, value, unit = "", note, tone = "", progress = null }) {
        const meter = progress === null ? "" : `
            <div class="metric-meter"><span style="width:${Math.max(0, Math.min(100, progress))}%"></span></div>`;
        return `
            <article class="metric-card ${tone}">
                <div class="metric-head">
                    <span class="metric-icon">${icon(iconName)}</span>
                    <span>${escapeHtml(label)}</span>
                </div>
                <div class="metric-value">${escapeHtml(value)}<small>${escapeHtml(unit)}</small></div>
                ${meter}
                <p>${escapeHtml(note || "")}</p>
            </article>`;
    }

    function renderMetrics(current, indices) {
        const uv = findIndex(indices, ["紫外线", "防晒"]);
        const aqi = current.air_quality?.score;
        const metrics = [
            metricCard({
                iconName: "humidity",
                label: "相对湿度",
                value: number(current.humidity),
                unit: "%",
                note: humidityNote(current.humidity),
                progress: current.humidity,
            }),
            metricCard({
                iconName: "wind",
                label: "风向风力",
                value: current.wind_direction || "暂无",
                unit: current.wind_level || "",
                note: current.wind_speed_kmh !== null ? `风速约 ${number(current.wind_speed_kmh)} km/h` : "官方实时观测",
                progress: Math.min(100, Number(current.wind_speed_kmh || 0) * 3),
            }),
            metricCard({
                iconName: "sun",
                label: "紫外线",
                value: uv?.hint || "暂无",
                unit: "",
                note: uv?.description || "当前暂无官方紫外线指数",
                tone: "warm",
                progress: uvProgress(uv?.hint),
            }),
            metricCard({
                iconName: "air",
                label: "空气质量",
                value: current.air_quality?.level || "暂无",
                unit: aqi === null ? "" : String(number(aqi)),
                note: current.pm25 !== null ? `PM2.5 ${number(current.pm25)} μg/m³` : "AQI 实时估算",
                tone: airTone(current.air_quality?.color),
                progress: Math.min(100, Number(aqi || 0) / 3),
            }),
            metricCard({
                iconName: "pressure",
                label: "气压",
                value: number(current.pressure_hpa),
                unit: "hPa",
                note: "气压变化可作为天气趋势参考",
                progress: Math.max(0, Math.min(100, (Number(current.pressure_hpa || 1010) - 960) / 0.8)),
            }),
            metricCard({
                iconName: "visibility",
                label: "能见度",
                value: formatSmallNumber(current.visibility_km),
                unit: "km",
                note: Number(current.visibility_km) < 5 ? "能见度偏低，出行注意安全" : "视野通透，注意远近光线变化",
                progress: Math.min(100, Number(current.visibility_km || 0) * 5),
            }),
        ];
        document.getElementById("metric-grid").innerHTML = metrics.join("");
    }

    function humidityNote(value) {
        const humidity = Number(value);
        if (Number.isNaN(humidity)) return "暂无湿度观测";
        if (humidity >= 80) return "空气潮湿，体感可能更闷";
        if (humidity <= 30) return "空气偏干，注意补水和保湿";
        return "湿度处于相对舒适区间";
    }

    function formatSmallNumber(value) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) return "--";
        return numeric < 10 ? numeric.toFixed(1).replace(/\.0$/, "") : String(Math.round(numeric));
    }

    function uvProgress(hint = "") {
        if (hint.includes("极强") || hint.includes("很强")) return 95;
        if (hint.includes("强")) return 75;
        if (hint.includes("中等")) return 52;
        if (hint.includes("弱")) return 24;
        return 15;
    }

    function airTone(color) {
        if (["fair", "poor", "bad", "severe"].includes(color)) return "warm";
        if (["excellent", "good"].includes(color)) return "green";
        return "";
    }

    function findIndex(indices, names) {
        return indices.find((item) => names.some((name) => String(item.name || "").includes(name)));
    }

    function renderForecast(forecast) {
        const strip = document.getElementById("forecast-strip");
        strip.innerHTML = forecast.map((day, index) => `
            <article class="forecast-card ${index === 0 ? "today" : ""}">
                <span class="forecast-day">${escapeHtml(day.is_today ? "今天" : day.date_label || day.weekday)}</span>
                <span class="forecast-weekday">${escapeHtml(day.weekday || "")}</span>
                <span class="forecast-icon">${weatherSvg(day.icon)}</span>
                <strong>${escapeHtml(day.weather || "暂无")}</strong>
                <div class="forecast-temp">
                    <span>${number(day.temperature_low)}°</span>
                    <i></i>
                    <span>${number(day.temperature_high)}°</span>
                </div>
                <p>${escapeHtml(day.wind_direction || "暂无")} ${escapeHtml(day.wind_level || "")}</p>
            </article>
        `).join("");
    }

    function renderRecommendations(recommendations) {
        const grid = document.getElementById("recommendation-grid");
        if (!recommendations.length) {
            grid.innerHTML = `<div class="empty-inline">暂无额外生活建议</div>`;
            return;
        }
        grid.innerHTML = recommendations.map((item, index) => `
            <article class="recommendation-card tone-${escapeHtml(item.tone || "neutral")}" style="--delay:${index * 45}ms">
                <div class="recommendation-head">
                    <span class="recommendation-icon">${icon(item.icon || "info")}</span>
                    <span class="priority-label">${item.priority === "high" ? "优先关注" : "生活提示"}</span>
                </div>
                <h3>${escapeHtml(item.title)}</h3>
                <p>${escapeHtml(item.text)}</p>
            </article>
        `).join("");
    }

    function renderIndices(indices) {
        const grid = document.getElementById("indices-grid");
        if (!indices.length) {
            grid.innerHTML = `<div class="empty-inline">当前没有返回官方生活指数</div>`;
            return;
        }
        grid.innerHTML = indices.map((item) => `
            <button class="index-card tone-${escapeHtml(item.tone || "neutral")}" type="button" aria-expanded="false">
                <span class="index-name">${escapeHtml(item.name)}</span>
                <strong>${escapeHtml(item.hint)}</strong>
                <p>${escapeHtml(item.description)}</p>
                <span class="index-more">点击展开 ${icon("arrow")}</span>
            </button>
        `).join("");
        grid.querySelectorAll(".index-card").forEach((card) => {
            card.addEventListener("click", () => {
                const expanded = card.classList.toggle("expanded");
                card.setAttribute("aria-expanded", String(expanded));
            });
        });
    }

    function renderTrendChart(forecast) {
        const chart = document.getElementById("trend-chart");
        const validHigh = forecast.filter((day) => Number.isFinite(Number(day.temperature_high)));
        const validLow = forecast.filter((day) => Number.isFinite(Number(day.temperature_low)));
        if (forecast.length < 2 || (!validHigh.length && !validLow.length)) {
            chart.innerHTML = `<div class="chart-empty">暂无足够的温度数据绘制趋势</div>`;
            return;
        }

        const width = 900;
        const height = 310;
        const padding = { left: 46, right: 26, top: 34, bottom: 54 };
        const temperatures = forecast.flatMap((day) => [day.temperature_high, day.temperature_low])
            .map(Number)
            .filter(Number.isFinite);
        const minTemp = Math.min(...temperatures) - 2;
        const maxTemp = Math.max(...temperatures) + 2;
        const plotWidth = width - padding.left - padding.right;
        const plotHeight = height - padding.top - padding.bottom;
        const x = (index) => padding.left + (plotWidth * index) / Math.max(forecast.length - 1, 1);
        const y = (value) => padding.top + plotHeight - ((value - minTemp) / Math.max(maxTemp - minTemp, 1)) * plotHeight;

        const highPoints = forecast.map((day, index) => ({ x: x(index), y: y(Number(day.temperature_high)), value: day.temperature_high, date: day.date_label }))
            .filter((point) => Number.isFinite(Number(point.value)));
        const lowPoints = forecast.map((day, index) => ({ x: x(index), y: y(Number(day.temperature_low)), value: day.temperature_low, date: day.date_label }))
            .filter((point) => Number.isFinite(Number(point.value)));

        const gridLines = Array.from({ length: 5 }, (_, index) => {
            const value = minTemp + ((maxTemp - minTemp) * index) / 4;
            const lineY = y(value);
            return `
                <line x1="${padding.left}" y1="${lineY}" x2="${width - padding.right}" y2="${lineY}" class="chart-grid-line"/>
                <text x="${padding.left - 12}" y="${lineY + 4}" text-anchor="end" class="chart-axis-label">${Math.round(value)}°</text>`;
        }).join("");

        const dateLabels = forecast.map((day, index) => `
            <text x="${x(index)}" y="${height - 20}" text-anchor="middle" class="chart-date-label">${escapeHtml(day.is_today ? "今天" : day.weekday || day.date_label)}</text>
        `).join("");

        const highPath = smoothPath(highPoints);
        const lowPath = smoothPath(lowPoints);
        const areaPath = highPoints.length
            ? `${highPath} L ${highPoints.at(-1).x} ${height - padding.bottom} L ${highPoints[0].x} ${height - padding.bottom} Z`
            : "";

        const pointsSvg = (points, className) => points.map((point) => `
            <g class="chart-point ${className}">
                <circle cx="${point.x}" cy="${point.y}" r="10" class="point-halo"></circle>
                <circle cx="${point.x}" cy="${point.y}" r="4.2"></circle>
                <text x="${point.x}" y="${point.y - 15}" text-anchor="middle">${Math.round(Number(point.value))}°</text>
                <title>${escapeHtml(point.date)}：${point.value}°C</title>
            </g>
        `).join("");

        chart.innerHTML = `
            <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
                <defs>
                    <linearGradient id="highLine" x1="0" y1="0" x2="1" y2="0">
                        <stop offset="0" stop-color="#d7ff79"/>
                        <stop offset="1" stop-color="#7ff0d4"/>
                    </linearGradient>
                    <linearGradient id="highArea" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0" stop-color="#caff70" stop-opacity=".22"/>
                        <stop offset="1" stop-color="#caff70" stop-opacity="0"/>
                    </linearGradient>
                </defs>
                ${gridLines}
                ${dateLabels}
                ${areaPath ? `<path d="${areaPath}" fill="url(#highArea)"/>` : ""}
                ${highPath ? `<path d="${highPath}" class="chart-line high-line"/>` : ""}
                ${lowPath ? `<path d="${lowPath}" class="chart-line low-line"/>` : ""}
                ${pointsSvg(highPoints, "high-point")}
                ${pointsSvg(lowPoints, "low-point")}
            </svg>`;
    }

    function smoothPath(points) {
        if (!points.length) return "";
        if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
        let path = `M ${points[0].x} ${points[0].y}`;
        for (let i = 0; i < points.length - 1; i += 1) {
            const current = points[i];
            const next = points[i + 1];
            const middle = (current.x + next.x) / 2;
            path += ` C ${middle} ${current.y}, ${middle} ${next.y}, ${next.x} ${next.y}`;
        }
        return path;
    }

    function normalizeWeatherKind(value = "") {
        const text = String(value);
        if (text.includes("thunder") || text.includes("雷")) return "thunder";
        if (text.includes("snow") || text.includes("雪")) return "snow";
        if (text.includes("rain") || text.includes("雨")) return "rain";
        if (text.includes("fog") || text.includes("雾") || text.includes("霾")) return "fog";
        if (text.includes("wind") || text.includes("风")) return "wind";
        if (text.includes("overcast") || text.includes("阴")) return "overcast";
        if (text.includes("cloud") || text.includes("云")) return "cloud";
        return "sun";
    }

    function weatherSvg(kind) {
        const normalized = normalizeWeatherKind(kind);
        const commonSun = `<circle cx="17" cy="14" r="5" fill="#e6ff9d"/>`;
        const cloud = `<path d="M8 29h19a6 6 0 0 0 .4-12A9 9 0 0 0 10 19a5 5 0 0 0-2 10Z" fill="currentColor"/>`;
        const rain = `<path d="m14 33-2 5M22 33l-2 5M30 33l-2 5" stroke="#72dfe7" stroke-width="2" stroke-linecap="round"/>`;
        const snow = `<path d="M14 35v6M11 38h6M24 35v6M21 38h6M34 35v6M31 38h6" stroke="#b9efff" stroke-width="1.6" stroke-linecap="round"/>`;
        const content = {
            sun: `<circle cx="22" cy="20" r="10" fill="#e6ff9d"/><path d="M22 3v5M22 32v5M5 20h5M34 20h5M10 8l4 4M30 28l4 4M10 32l4-4M30 12l4-4" stroke="#e6ff9d" stroke-width="2" stroke-linecap="round"/>`,
            cloud: `${commonSun}${cloud}`,
            overcast: `${cloud}<path d="M4 21h22a6 6 0 0 0 0-12 8 8 0 0 0-14 1A6 6 0 0 0 4 21Z" fill="currentColor" opacity=".55"/>`,
            rain: `${cloud}${rain}`,
            thunder: `${cloud}<path d="m22 29-5 8h5l-2 6 9-11h-6l3-3Z" fill="#f4ff91"/>`,
            snow: `${cloud}${snow}`,
            fog: `${cloud}<path d="M9 36h24M13 41h20M7 46h19" stroke="currentColor" stroke-width="2" stroke-linecap="round" opacity=".55"/>`,
            wind: `<path d="M5 15h23a4 4 0 1 0-3.3-6.2M5 24h31a4 4 0 1 1-3.3 6.2M5 33h17" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>`,
        };
        return `<svg class="weather-inline-svg" viewBox="0 0 44 50" aria-hidden="true">${content[normalized] || content.sun}</svg>`;
    }

    function setupHeader() {
        const form = document.getElementById("header-search-form");
        const input = document.getElementById("header-city-search");
        if (form && input) {
            new Autocomplete(input.closest("[data-autocomplete]"), input, {
                onSelect: (city) => navigateToWeather(city.name),
            });
            form.addEventListener("submit", (event) => {
                event.preventDefault();
                const city = input.value.trim();
                if (city) navigateToWeather(city);
            });
        }
        document.getElementById("header-location")?.addEventListener("click", () => locateCity());
    }

    setupHeader();
    const city = queryCity();
    if (!city) {
        showError({ code: "CITY_REQUIRED", message: "请选择一个城市开始观察。" }, "首页");
    } else {
        loadWeather(city);
    }
})();
