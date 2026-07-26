function MetaGuidesPanel({ guides }) {
    const GUIDE_LIMIT = 5;
    const rows = (Array.isArray(guides) ? guides : [])
        .filter((row) => row && row.hero_name && row.hero_name !== "unknown")
        .slice(0, GUIDE_LIMIT);

    const [activeHero, setActiveHero] = React.useState("");

    if (rows.length === 0) {
        return (
            <article className="panel meta-guides-panel">
                <div className="panel-title-row">
                    <h3>Гайды под твой пул</h3>
                </div>
                <p className="panel-placeholder">Загрузите профиль — подберём план по вашим героям</p>
            </article>
        );
    }

    const maxGames = Math.max(...rows.map((row) => Number(row.games) || 0), 1);

    const winrateTone = (winrate) => {
        const value = Number(winrate) || 0;
        if (value >= 55) return "high";
        if (value >= 48) return "mid";
        return "low";
    };

    return (
        <article className="panel meta-guides-panel">
            <div className="panel-title-row">
                <h3>Гайды под твой пул</h3>
                <span className="panel-subtitle">По вашим героям</span>
            </div>

            <div className="meta-guides-list">
                {rows.map((row, index) => {
                    const heroLabel = window.prettyHeroName(row.hero_name);
                    const games = Number(row.games) || 0;
                    const winrate = Number(row.winrate) || 0;
                    const tone = winrateTone(winrate);
                    const isActive = activeHero === row.hero_name;
                    // Полоса игр показывает долю от самого играемого героя, полоса
                    // винрейта - сам винрейт. Обе величины настоящие. Рост от нуля
                    // делает CSS-анимация: requestAnimationFrame здесь не годится,
                    // он не срабатывает, пока вкладка не отрисовывается, и полосы
                    // остались бы пустыми.
                    const gamesWidth = Math.max(6, (games / maxGames) * 100);
                    const winrateWidth = Math.max(4, Math.min(100, winrate));

                    return (
                        <div
                            className={`meta-guide-row${isActive ? " is-active" : ""}`}
                            key={`${row.hero_name}-${index}`}
                            onMouseEnter={() => setActiveHero(row.hero_name)}
                            onMouseLeave={() => setActiveHero("")}
                        >
                            <div className="meta-guide-rank">{index + 1}</div>

                            <div className="meta-guide-main">
                                <img
                                    src={row.hero_image}
                                    alt={heroLabel}
                                    className="meta-guide-hero"
                                    onError={(event) => {
                                        event.currentTarget.style.visibility = "hidden";
                                    }}
                                />
                                <div className="meta-guide-text">
                                    <strong>{heroLabel}</strong>
                                    <span>{row.role}</span>
                                </div>
                            </div>

                            <div className="meta-guide-stats">
                                <div className="meta-guide-numbers">
                                    <span>
                                        Игр: <b>{games}</b>
                                    </span>
                                    <span>
                                        WR: <b className={`meta-guide-wr ${tone}`}>{winrate}%</b>
                                    </span>
                                </div>

                                <div className="meta-guide-bars">
                                    <div className="meta-guide-track" title={`${games} игр`}>
                                        <div className="meta-guide-fill games" style={{ width: `${gamesWidth}%` }} />
                                    </div>
                                    <div className="meta-guide-track" title={`Винрейт ${winrate}%`}>
                                        <div className={`meta-guide-fill wr ${tone}`} style={{ width: `${winrateWidth}%` }} />
                                    </div>
                                </div>
                            </div>

                            <p className="meta-guide-focus">{row.focus}</p>
                        </div>
                    );
                })}
            </div>
        </article>
    );
}

window.MetaGuidesPanel = MetaGuidesPanel;
