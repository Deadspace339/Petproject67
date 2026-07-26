function TopHeroesCard({ topHeroes }) {
    const heroes = Array.isArray(topHeroes) ? topHeroes : [];
    const normalized = [...heroes];

    while (normalized.length < 5) {
        normalized.push(null);
    }

    return (
        <article className="panel top-heroes-card">
            <div className="panel-title-row">
                <h3>Топ Героев</h3>
            </div>

            <div className="top-heroes-grid">
                {heroes.length > 0 ? (
                    normalized.map((hero, index) =>
                        hero ? (
                            <div className="hero-card" key={hero.hero_name}>
                                <img
                                    src={`https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/${hero.hero_name}.png`}
                                    alt={hero.hero_name}
                                />
                                <div className="hero-meta">
                                    <strong>{hero.winrate}%</strong>
                                    <span>{hero.games} игр</span>
                                </div>
                            </div>
                        ) : (
                            <div className="hero-card hero-card-placeholder" key={`hero-placeholder-${index}`}>
                                <div className="hero-placeholder-thumb" />
                                <div className="hero-meta">
                                    <strong>-</strong>
                                    <span>нет данных</span>
                                </div>
                            </div>
                        ),
                    )
                ) : (
                    <p className="panel-placeholder">Герои появятся после анализа</p>
                )}
            </div>
        </article>
    );
}

window.TopHeroesCard = TopHeroesCard;
