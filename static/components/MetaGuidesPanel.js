function MetaGuidesPanel({ guides }) {
    const GUIDE_LIMIT = 5;
    const rows = (Array.isArray(guides) ? guides : [])
        .filter((row) => row && row.hero_name && row.hero_name !== "unknown")
        .slice(0, GUIDE_LIMIT);

    // Раскрыт всегда ровно один герой: панель узкая, и пять развёрнутых
    // руководств сразу превратили бы её в простыню.
    const [openHero, setOpenHero] = React.useState("");

    if (rows.length === 0) {
        return (
            <article className="panel meta-guides-panel">
                <div className="panel-title-row">
                    <h3>Руководства по твоим героям</h3>
                </div>
                <p className="panel-placeholder">Загрузите профиль — подберём план по вашим героям</p>
            </article>
        );
    }

    const activeHero = openHero || rows[0].hero_name;

    return (
        <article className="panel meta-guides-panel">
            <div className="panel-title-row">
                <h3>Руководства по твоим героям</h3>
                <span className="panel-subtitle">Нажмите на героя</span>
            </div>

            <div className="meta-guides-list">
                {rows.map((row, index) => {
                    const heroLabel = window.prettyHeroName(row.hero_name);
                    const isOpen = activeHero === row.hero_name;

                    return (
                        <div className={`guide-card${isOpen ? " is-open" : ""}`} key={`${row.hero_name}-${index}`}>
                            <button
                                type="button"
                                className="guide-head"
                                onClick={() => setOpenHero(isOpen ? "__none__" : row.hero_name)}
                                aria-expanded={isOpen}
                            >
                                <span className="guide-rank">{index + 1}</span>
                                <img
                                    src={row.hero_image}
                                    alt={heroLabel}
                                    className="guide-hero"
                                    onError={(event) => {
                                        event.currentTarget.style.visibility = "hidden";
                                    }}
                                />
                                <span className="guide-title">
                                    <strong>{heroLabel}</strong>
                                    <span className="guide-role">{row.role}</span>
                                </span>
                                <span className="guide-chevron" aria-hidden="true">
                                    {isOpen ? "−" : "+"}
                                </span>
                            </button>

                            <div className="guide-body">
                                <p className="guide-line">
                                    <span className="guide-label">План</span>
                                    {row.plan}
                                </p>
                                <p className="guide-line">
                                    <span className="guide-label">Начало</span>
                                    {row.early}
                                </p>
                                <p className="guide-line">
                                    <span className="guide-label">Сборка</span>
                                    {row.items}
                                </p>
                                <p className="guide-line warn">
                                    <span className="guide-label">Ошибка</span>
                                    {row.mistake}
                                </p>
                            </div>
                        </div>
                    );
                })}
            </div>
        </article>
    );
}

window.MetaGuidesPanel = MetaGuidesPanel;
