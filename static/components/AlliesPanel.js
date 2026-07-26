function AlliesPanel({ allies }) {
    const allyList = [...(allies || [])].sort((left, right) => {
        const leftGames = Number(left?.games || 0);
        const rightGames = Number(right?.games || 0);
        if (rightGames !== leftGames) {
            return rightGames - leftGames;
        }

        const leftWins = Number(left?.wins || 0);
        const rightWins = Number(right?.wins || 0);
        return rightWins - leftWins;
    });
    const maxGames = allyList.length > 0 ? Math.max(...allyList.map((ally) => ally.games || 0), 1) : 1;

    return (
        <article className="panel allies-panel">
            <div className="panel-title-row">
                <h3>Союзники</h3>
            </div>

            {allyList.length > 0 ? (
                <div className="stats-list">
                    <div className="stats-row stats-row-header ally-row" aria-hidden="true">
                        <div className="stats-head-cell">Игрок</div>
                        <div className="stats-head-cell">Процент побед</div>
                        <div className="stats-head-cell">Матчи</div>
                    </div>

                    {allyList.map((ally, index) => {
                        const gamesWidth = Math.max(8, ((ally.games || 0) / maxGames) * 100);
                        const shortName = ally.name && ally.name.length > 12 ? `${ally.name.slice(0, 12)}...` : ally.name;

                        return (
                            <div className="stats-row ally-row" key={`${ally.name}-${index}`}>
                                <div className="stats-entity">
                                    {ally.avatar ? (
                                        <img src={ally.avatar} alt={ally.name} className="stats-ally-img" />
                                    ) : (
                                        <div className="stats-ally-fallback">{(ally.name || "?").slice(0, 1)}</div>
                                    )}
                                    <div>
                                        <div className="stats-name" title={ally.name || "Unknown"}>
                                            {shortName || "Unknown"}
                                        </div>
                                    </div>
                                </div>

                                <div className="stats-track-block">
                                    <span className={`stats-value ${ally.winrate >= 50 ? "good" : "bad"}`}>
                                        {ally.winrate}%
                                    </span>
                                    <div className="stats-track">
                                        <div
                                            className={`stats-fill ${ally.winrate >= 50 ? "good" : "bad"}`}
                                            style={{ width: `${Math.max(8, ally.winrate)}%` }}
                                        />
                                    </div>
                                </div>

                                <div className="stats-track-block">
                                    <span className="stats-value warm">{ally.games}</span>
                                    <div className="stats-track warm">
                                        <div className="stats-fill warm" style={{ width: `${gamesWidth}%` }} />
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            ) : (
                <p className="panel-placeholder">Нет данных по союзникам</p>
            )}
        </article>
    );
}

window.AlliesPanel = AlliesPanel;

