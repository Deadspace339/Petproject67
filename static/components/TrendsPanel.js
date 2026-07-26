function polarToCartesian(cx, cy, radius, angleDeg) {
    const radians = (angleDeg - 90) * (Math.PI / 180);
    return {
        x: cx + radius * Math.cos(radians),
        y: cy + radius * Math.sin(radians),
    };
}

function donutSectorPath(cx, cy, innerRadius, outerRadius, startDeg, endDeg) {
    const outerStart = polarToCartesian(cx, cy, outerRadius, endDeg);
    const outerEnd = polarToCartesian(cx, cy, outerRadius, startDeg);
    const innerStart = polarToCartesian(cx, cy, innerRadius, startDeg);
    const innerEnd = polarToCartesian(cx, cy, innerRadius, endDeg);

    const largeArcFlag = endDeg - startDeg <= 180 ? "0" : "1";

    return [
        `M ${outerStart.x} ${outerStart.y}`,
        `A ${outerRadius} ${outerRadius} 0 ${largeArcFlag} 0 ${outerEnd.x} ${outerEnd.y}`,
        `L ${innerStart.x} ${innerStart.y}`,
        `A ${innerRadius} ${innerRadius} 0 ${largeArcFlag} 1 ${innerEnd.x} ${innerEnd.y}`,
        "Z",
    ].join(" ");
}

function clampPercent(value) {
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
        return 0;
    }
    return Math.max(0, Math.min(100, numericValue));
}

function resolveEfficiencyStrokeColor(value) {
    if (value >= 55) {
        return "rgba(28, 225, 124, 0.96)";
    }
    if (value <= 45) {
        return "rgba(255, 102, 77, 0.96)";
    }
    return "rgba(241, 204, 67, 0.96)";
}

const RADAR_BENCHMARK_DEFAULTS = {
    farming: 82,
    fighting: 78,
    survivability: 80,
    experience: 84,
    versatility: 72,
};

function TrendsPanel({ stats, selectedWindow, onWindowChange, hasWindow100 }) {
    const safeStats = stats || {};
    const radar = safeStats.radar_data || {};
    const benchmark = { ...RADAR_BENCHMARK_DEFAULTS, ...(safeStats.radar_benchmark || {}) };
    const efficiency = safeStats.radar_efficiency || {};
    const heroRing = Array.isArray(safeStats.hero_ring) ? safeStats.hero_ring : [];

    const wheelItems = [
        { key: "farming", label: "Farm", color: "#5b3cd9", icon: "⛏" },
        { key: "fighting", label: "Fight", color: "#cf8b22", icon: "⚔" },
        { key: "survivability", label: "Survive", color: "#d9414d", icon: "🛡" },
        { key: "experience", label: "Exp", color: "#2692b0", icon: "🧪" },
        { key: "versatility", label: "Vers", color: "#2f9753", icon: "🧠" },
    ];

    const center = 170;
    const innerRadius = 58;
    const outerRadius = 118;
    const iconRadius = 142;

    const bars = Array.isArray(safeStats.trend_points)
        ? safeStats.trend_points.slice(-(selectedWindow === 100 ? 60 : 25))
        : [];

    const windowWins = Number.isFinite(Number(safeStats.wins)) ? Number(safeStats.wins) : 0;
    const windowLosses = Number.isFinite(Number(safeStats.losses)) ? Number(safeStats.losses) : 0;
    const windowMatchCount = Number.isFinite(Number(safeStats.matches))
        ? Number(safeStats.matches)
        : Number.isFinite(Number(selectedWindow))
          ? Number(selectedWindow)
          : 25;

    const deltaValue = safeStats.winrate_delta || 0;
    const deltaText = deltaValue > 0 ? `+${deltaValue}%` : `${deltaValue}%`;
    const deltaClass = deltaValue > 0 ? "trend-good" : deltaValue < 0 ? "trend-bad" : "trend-neutral";

    return (
        <article className="panel trends-panel">
            <div className="trends-header">
                <h3>Тренды</h3>
                <div className="window-switch" role="group" aria-label="Window switch">
                    <button
                        className={`window-btn ${selectedWindow === 25 ? "active" : ""}`}
                        onClick={() => onWindowChange(25)}
                    >
                        25 Матчей
                    </button>
                    <button
                        className={`window-btn ${selectedWindow === 100 ? "active" : ""}`}
                        onClick={() => onWindowChange(100)}
                        disabled={!hasWindow100}
                    >
                        100
                    </button>
                </div>
            </div>

            {stats ? (
                <>
                    <div className="wheel-layout">
                        <div className="trend-wheel-wrap">
                            <svg className="trend-wheel-svg" viewBox="0 0 340 340" aria-hidden="true">
                                <circle cx={center} cy={center} r={152} className="wheel-outer-ring" />
                                {wheelItems.map((item, index) => {
                                    const benchmarkValue = clampPercent(benchmark[item.key] || 0);
                                    const start = index * (360 / wheelItems.length);
                                    const end = (index + 1) * (360 / wheelItems.length);
                                    const benchmarkOuterRadius =
                                        innerRadius + ((outerRadius - innerRadius) * benchmarkValue) / 100;
                                    const path = donutSectorPath(
                                        center,
                                        center,
                                        innerRadius,
                                        benchmarkOuterRadius,
                                        start,
                                        end,
                                    );

                                    return (
                                        <path
                                            key={`benchmark-${item.key}`}
                                            d={path}
                                            fill="rgba(174, 184, 198, 0.13)"
                                            stroke="rgba(206, 214, 224, 0.38)"
                                            strokeWidth="1"
                                            strokeDasharray="3 3"
                                        />
                                    );
                                })}
                                {wheelItems.map((item, index) => {
                                    const value = clampPercent(radar[item.key] || 0);
                                    const efficiencyScore = clampPercent(efficiency[item.key] || 0);
                                    const start = index * (360 / wheelItems.length);
                                    const end = (index + 1) * (360 / wheelItems.length);
                                    const opacity = 0.15 + (value / 100) * 0.65;
                                    const path = donutSectorPath(center, center, innerRadius, outerRadius, start, end);

                                    return (
                                        <path
                                            key={item.key}
                                            d={path}
                                            fill={item.color}
                                            fillOpacity={opacity}
                                            stroke={resolveEfficiencyStrokeColor(efficiencyScore)}
                                            strokeWidth="2"
                                        />
                                    );
                                })}
                                <circle cx={center} cy={center} r={45} className="wheel-inner-hole" />
                            </svg>

                            <div className="wheel-center-value">
                                <span>{stats.matches}</span>
                                <small>матчей</small>
                            </div>

                            {wheelItems.map((item, index) => {
                                const angle = index * (360 / wheelItems.length);
                                const pos = polarToCartesian(center, center, 88, angle);
                                return (
                                    <div
                                        key={`${item.key}-icon`}
                                        className="wheel-stat-icon"
                                        style={{ left: `${pos.x}px`, top: `${pos.y}px` }}
                                        title={`${item.label}: ${radar[item.key] || 0}`}
                                    >
                                        {item.icon}
                                    </div>
                                );
                            })}

                            {heroRing.slice(0, 12).map((hero, index) => {
                                const angle = (360 / Math.max(heroRing.length, 1)) * index;
                                const pos = polarToCartesian(center, center, iconRadius, angle);
                                const heroLabel = (hero || "unknown").replace(/_/g, " ");

                                return (
                                    <img
                                        key={`${hero}-${index}`}
                                        className="wheel-hero-icon"
                                        src={`https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/${hero}.png`}
                                        alt={heroLabel}
                                        title={heroLabel}
                                        style={{ left: `${pos.x}px`, top: `${pos.y}px` }}
                                    />
                                );
                            })}
                        </div>
                    </div>
                    <div className="wheel-context-hint">
                        <span className="legend-chip benchmark">Пунктир: эталон Immortal</span>
                        <span className="legend-chip high">Контур 55%+: зона силы</span>
                        <span className="legend-chip medium">Контур 45-55%: средне</span>
                        <span className="legend-chip low">Контур до 45%: зона риска</span>
                    </div>

                    <div className="trend-bars-wrap">
                        <div className="trend-bars">
                            {bars.map((point, index) => (
                                <div
                                    key={`bar-${index}`}
                                    className={`trend-bar ${point.result > 0 ? "win" : "loss"}`}
                                    title={`${point.hero_name || "unknown"} (${point.result > 0 ? "W" : "L"})`}
                                />
                            ))}
                        </div>
                        <div className="trend-dots">
                            {bars.map((point, index) => (
                                <span key={`dot-${index}`} className={`trend-dot ${point.result > 0 ? "win" : "loss"}`} />
                            ))}
                        </div>
                    </div>

                    <div className="trend-summary-grid">
                        <div className="trend-summary-item">
                            <span>Показатель побед в матчах</span>
                            <b>
                                {stats.recent_wr}% <i className={deltaClass}>{deltaText}</i>
                            </b>
                        </div>
                        <div className="trend-summary-item">
                            <span>Запись за окно</span>
                            <b className="lane-record-value">
                                <span className="lane-chunk lane-win">
                                    <span className="lane-caption">Победы</span>
                                    <span className="lane-num">{windowWins}</span>
                                </span>
                                <span className="lane-separator">-</span>
                                <span className="lane-chunk lane-loss">
                                    <span className="lane-caption">Поражения</span>
                                    <span className="lane-num">{windowLosses}</span>
                                </span>
                                <span className="lane-separator">-</span>
                                <span className="lane-chunk lane-window">
                                    <span className="lane-caption">Матчей</span>
                                    <span className="lane-num">{windowMatchCount}</span>
                                </span>
                            </b>
                        </div>
                        <div className="trend-summary-item">
                            <span>Групповой подбор</span>
                            <b>{stats.party_rate}%</b>
                        </div>
                        <div className="trend-summary-item">
                            <span>Обычная (соло)</span>
                            <b>{stats.solo_rate}%</b>
                        </div>
                    </div>
                </>
            ) : (
                <p className="panel-placeholder">Загрузите игрока, чтобы увидеть тренды.</p>
            )}
        </article>
    );
}

window.TrendsPanel = TrendsPanel;
