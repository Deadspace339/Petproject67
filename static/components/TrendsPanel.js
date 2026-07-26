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

function num(value, digits) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return 0;
    return digits ? Math.round(parsed * 10 ** digits) / 10 ** digits : parsed;
}

// Каждый сектор колеса объясняет сам себя: на что он смотрит и из какой реальной
// метрики посчитан. Раньше иконки были просто картинками без смысла.
const WHEEL_METRICS = [
    {
        key: "farming",
        label: "Фарм",
        icon: "⛏",
        read: (s) => ({ value: num(s.avg_gpm), unit: "GPM", hint: "Золота в минуту" }),
    },
    {
        key: "fighting",
        label: "Драки",
        icon: "⚔",
        read: (s) => ({ value: num(num(s.avg_kills) + num(s.avg_assists), 1), unit: "K+A", hint: "Убийств и помощей за матч" }),
    },
    {
        key: "survivability",
        label: "Живучесть",
        icon: "🛡",
        read: (s) => ({ value: num(s.avg_kda, 2), unit: "KDA", hint: `Смертей за матч: ${num(s.avg_deaths, 1)}` }),
    },
    {
        key: "experience",
        label: "Опыт",
        icon: "🧪",
        read: (s) => ({ value: num(s.avg_xpm), unit: "XPM", hint: "Опыта в минуту" }),
    },
    {
        key: "versatility",
        label: "Пул",
        icon: "🎭",
        read: (s) => ({ value: num(s.unique_heroes), unit: "героев", hint: "Разных героев в окне" }),
    },
];

function TrendsPanel({ stats, windows, selectedWindow, onWindowChange, hasWindow100 }) {
    const safeStats = stats || {};
    const radar = safeStats.radar_data || {};
    const heroRing = Array.isArray(safeStats.hero_ring) ? safeStats.hero_ring : [];

    // Пунктир — это второе окно того же игрока, а не выдуманный «эталон Immortal»,
    // который тут стоял раньше захардкоженными числами. Сравнение 25 против 100
    // показывает реальное изменение формы.
    const otherKey = selectedWindow === 100 ? "25" : "100";
    const otherStats = windows && windows[otherKey] && windows[otherKey].matches > 0 ? windows[otherKey] : null;
    const otherRadar = otherStats ? otherStats.radar_data || {} : null;

    const [selection, setSelection] = React.useState(null);

    const center = 170;
    const innerRadius = 58;
    const outerRadius = 118;
    const iconRadius = 142;
    const step = 360 / WHEEL_METRICS.length;

    const bars = Array.isArray(safeStats.trend_points)
        ? safeStats.trend_points.slice(-(selectedWindow === 100 ? 60 : 25))
        : [];

    const windowWins = num(safeStats.wins);
    const windowLosses = num(safeStats.losses);
    const windowMatchCount = num(safeStats.matches);

    const deltaValue = safeStats.winrate_delta || 0;
    const deltaText = deltaValue > 0 ? `+${deltaValue}%` : `${deltaValue}%`;
    const deltaClass = deltaValue > 0 ? "trend-good" : deltaValue < 0 ? "trend-bad" : "trend-neutral";

    const selectedMetric =
        selection && selection.type === "metric" ? WHEEL_METRICS.find((m) => m.key === selection.key) : null;
    const selectedHero =
        selection && selection.type === "hero" ? heroRing.find((h) => h.hero_name === selection.key) : null;

    const renderCenter = () => {
        if (selectedHero) {
            const wr = num(selectedHero.winrate, 1);
            return (
                <div className="wheel-center-panel hero">
                    <strong className="wheel-center-title">{window.prettyHeroName(selectedHero.hero_name)}</strong>
                    <span className={`wheel-center-main ${wr >= 50 ? "good" : "bad"}`}>{wr}%</span>
                    <span className="wheel-center-sub">
                        {selectedHero.wins}П – {selectedHero.losses}О за {selectedHero.games} игр
                    </span>
                    <span className="wheel-center-sub">
                        KDA {selectedHero.avg_kda} · {selectedHero.avg_kills}/{selectedHero.avg_deaths}/
                        {selectedHero.avg_assists}
                        {selectedHero.avg_gpm > 0 ? ` · ${selectedHero.avg_gpm} GPM` : ""}
                    </span>
                </div>
            );
        }

        if (selectedMetric) {
            const detail = selectedMetric.read(safeStats);
            const score = clampPercent(radar[selectedMetric.key] || 0);
            const otherScore = otherRadar ? clampPercent(otherRadar[selectedMetric.key] || 0) : null;
            const diff = otherScore === null ? null : score - otherScore;

            return (
                <div className="wheel-center-panel metric">
                    <strong className="wheel-center-title">{selectedMetric.label}</strong>
                    <span className="wheel-center-main">
                        {detail.value}
                        <small> {detail.unit}</small>
                    </span>
                    <span className="wheel-center-sub">{detail.hint}</span>
                    {diff === null ? (
                        <span className="wheel-center-sub">нет данных по окну {otherKey}</span>
                    ) : Math.round(diff) === 0 ? (
                        <span className="wheel-center-sub">как в окне {otherKey}</span>
                    ) : (
                        <span className={`wheel-center-sub ${diff > 0 ? "trend-good" : "trend-bad"}`}>
                            {diff > 0 ? "выше" : "ниже"} окна {otherKey} на {Math.abs(Math.round(diff))}
                        </span>
                    )}
                </div>
            );
        }

        return (
            <div className="wheel-center-panel">
                <span className="wheel-center-main">{windowMatchCount}</span>
                <span className="wheel-center-sub">матчей в окне</span>
                <span className="wheel-center-hint">Нажмите на сектор или героя</span>
            </div>
        );
    };

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
                            <svg className="trend-wheel-svg" viewBox="0 0 340 340">
                                <defs>
                                    <linearGradient id="wheelRed" x1="0" y1="0" x2="1" y2="1">
                                        <stop offset="0%" stopColor="#7a1020" />
                                        <stop offset="55%" stopColor="#d8263a" />
                                        <stop offset="100%" stopColor="#ff6a5a" />
                                    </linearGradient>
                                </defs>

                                <circle cx={center} cy={center} r={152} className="wheel-outer-ring" />

                                {WHEEL_METRICS.map((item, index) => {
                                    const value = clampPercent(radar[item.key] || 0);
                                    const isActive = selection && selection.type === "metric" && selection.key === item.key;
                                    const start = index * step;
                                    const end = (index + 1) * step;
                                    const path = donutSectorPath(center, center, innerRadius, outerRadius, start, end);

                                    return (
                                        <path
                                            key={item.key}
                                            d={path}
                                            fill="url(#wheelRed)"
                                            fillOpacity={0.2 + (value / 100) * 0.75}
                                            stroke={isActive ? "#ffd7cf" : "rgba(255, 255, 255, 0.16)"}
                                            strokeWidth={isActive ? 2.5 : 1}
                                            className="wheel-sector"
                                            onClick={() =>
                                                setSelection(isActive ? null : { type: "metric", key: item.key })
                                            }
                                        >
                                            <title>{`${item.label}: ${value} из 100`}</title>
                                        </path>
                                    );
                                })}

                                {/* Пунктир второго окна: видно, вырос показатель или просел. */}
                                {otherRadar
                                    ? WHEEL_METRICS.map((item, index) => {
                                          const otherValue = clampPercent(otherRadar[item.key] || 0);
                                          const radius = innerRadius + ((outerRadius - innerRadius) * otherValue) / 100;
                                          const start = index * step + 1.5;
                                          const end = (index + 1) * step - 1.5;
                                          const from = polarToCartesian(center, center, radius, start);
                                          const to = polarToCartesian(center, center, radius, end);
                                          return (
                                              <path
                                                  key={`ref-${item.key}`}
                                                  d={`M ${from.x} ${from.y} A ${radius} ${radius} 0 0 1 ${to.x} ${to.y}`}
                                                  fill="none"
                                                  stroke="rgba(233, 238, 245, 0.75)"
                                                  strokeWidth="2"
                                                  strokeDasharray="4 3"
                                                  pointerEvents="none"
                                              />
                                          );
                                      })
                                    : null}

                                <circle cx={center} cy={center} r={45} className="wheel-inner-hole" />
                            </svg>

                            <div className="wheel-center-value">{renderCenter()}</div>

                            {WHEEL_METRICS.map((item, index) => {
                                const pos = polarToCartesian(center, center, 88, index * step + step / 2);
                                const isActive = selection && selection.type === "metric" && selection.key === item.key;
                                return (
                                    <button
                                        key={`${item.key}-icon`}
                                        type="button"
                                        className={`wheel-stat-icon${isActive ? " is-active" : ""}`}
                                        style={{ left: `${pos.x}px`, top: `${pos.y}px` }}
                                        title={`${item.label} — ${item.read(safeStats).hint}`}
                                        onClick={() => setSelection(isActive ? null : { type: "metric", key: item.key })}
                                    >
                                        <span className="wheel-stat-glyph">{item.icon}</span>
                                        <span className="wheel-stat-label">{item.label}</span>
                                    </button>
                                );
                            })}

                            {heroRing.slice(0, 12).map((hero, index) => {
                                const angle = (360 / Math.max(Math.min(heroRing.length, 12), 1)) * index;
                                const pos = polarToCartesian(center, center, iconRadius, angle);
                                const heroLabel = window.prettyHeroName(hero.hero_name);
                                const isActive = selection && selection.type === "hero" && selection.key === hero.hero_name;

                                return (
                                    <button
                                        key={`${hero.hero_name}-${index}`}
                                        type="button"
                                        className={`wheel-hero-btn${isActive ? " is-active" : ""}`}
                                        style={{ left: `${pos.x}px`, top: `${pos.y}px` }}
                                        title={`${heroLabel}: ${hero.winrate}% за ${hero.games} игр`}
                                        onClick={() => setSelection(isActive ? null : { type: "hero", key: hero.hero_name })}
                                    >
                                        <img
                                            className="wheel-hero-icon"
                                            src={`https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/${hero.hero_name}.png`}
                                            alt={heroLabel}
                                        />
                                        <span className={`wheel-hero-dot ${hero.winrate >= 50 ? "good" : "bad"}`} />
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    <div className="wheel-context-hint">
                        <span className="legend-chip filled">Заливка: показатель окна {selectedWindow}</span>
                        <span className="legend-chip benchmark">Пунктир: то же за окно {otherKey}</span>
                        <span className="legend-chip dot-good">Точка у героя: винрейт 50%+</span>
                    </div>

                    <div className="trend-bars-wrap">
                        <div className="trend-bars">
                            {bars.map((point, index) => (
                                <div
                                    key={`bar-${index}`}
                                    className={`trend-bar ${point.result > 0 ? "win" : "loss"}`}
                                    title={`${window.prettyHeroName(point.hero_name)} (${point.result > 0 ? "W" : "L"})`}
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
