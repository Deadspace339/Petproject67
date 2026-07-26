function MostPlayedHeroesPanel({ heroes }) {
    const heroList = heroes || [];
    const maxGames = heroList.length > 0 ? Math.max(...heroList.map((hero) => hero.games || 0), 1) : 1;

    return (
        <article className="panel most-played-panel">
            <div className="panel-title-row">
                <h3>Самые играемые герои</h3>
                <span className="panel-subtitle">Топ {heroList.length || 5}</span>
            </div>

            {heroList.length > 0 ? (
                <div className="stats-list">
                    <div className="stats-row stats-row-header" aria-hidden="true">
                        <div className="stats-head-cell">Герой</div>
                        <div className="stats-head-cell">Процент побед</div>
                        <div className="stats-head-cell">Матчи</div>
                    </div>

                    {heroList.map((hero) => {
                        const heroLabel = window.prettyHeroName(hero.hero_name);
                        const gamesWidth = Math.max(8, ((hero.games || 0) / maxGames) * 100);

                        return (
                            <div className="stats-row" key={hero.hero_name}>
                                <div className="stats-entity">
                                    <img
                                        src={`https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/${hero.hero_name}.png`}
                                        alt={heroLabel}
                                        className="stats-hero-img"
                                    />
                                    <div>
                                        <div className="stats-name">{heroLabel}</div>
                                        <div className="stats-sub">{hero.pick_rate}% пикрейта</div>
                                    </div>
                                </div>

                                <div className="stats-track-block">
                                    <span className={`stats-value ${hero.winrate >= 50 ? "good" : "bad"}`}>
                                        {hero.winrate}%
                                    </span>
                                    <div className="stats-track">
                                        <div
                                            className={`stats-fill ${hero.winrate >= 50 ? "good" : "bad"}`}
                                            style={{ width: `${Math.max(8, hero.winrate)}%` }}
                                        />
                                    </div>
                                </div>

                                <div className="stats-track-block">
                                    <span className="stats-value warm">{hero.games}</span>
                                    <div className="stats-track warm">
                                        <div className="stats-fill warm" style={{ width: `${gamesWidth}%` }} />
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            ) : (
                <p className="panel-placeholder">Недостаточно данных по героям</p>
            )}
        </article>
    );
}

window.MostPlayedHeroesPanel = MostPlayedHeroesPanel;
