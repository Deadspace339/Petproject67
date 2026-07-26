function formatImpact(value) {
    const numeric = Number(value);
    const impact = Number.isFinite(numeric) ? numeric : 0;
    return impact >= 0 ? `+${impact}` : `${impact}`;
}

function MatchesTable({ matches }) {
    const matchList = Array.isArray(matches) ? matches : [];

    return (
        <article className="panel matches-panel">
            <div className="panel-title-row">
                <h3>{"\u041D\u0435\u0434\u0430\u0432\u043D\u0438\u0435 \u041C\u0430\u0442\u0447\u0438"}</h3>
                <span className="panel-subtitle">{"\u041F\u043E\u0441\u043B\u0435\u0434\u043D\u0438\u0435 10 \u043C\u0430\u0442\u0447\u0435\u0439"}</span>
            </div>

            {matchList.length > 0 ? (
                <div className="matches-list">
                    {matchList.map((match, index) => {
                        const isWin =
                            typeof match.is_win === "boolean"
                                ? match.is_win
                                : (match.player_slot < 128 && match.radiant_win) ||
                                  (match.player_slot >= 128 && !match.radiant_win);
                        const heroName = match.hero_name || "unknown";
                        const heroLabel = window.prettyHeroName(heroName);
                        const heroImage =
                            match.hero_image ||
                            `https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/${heroName}.png`;
                        const items = Array.isArray(match.items) ? match.items : [];
                        const displayItems =
                            items.length > 0
                                ? items
                                : Array.from({ length: 6 }).map((_, slotIndex) => ({
                                      id: `empty-${slotIndex}`,
                                      name: "Empty slot",
                                      image: "",
                                      is_empty: true,
                                  }));

                        return (
                            <div className="match-row-card" key={`${match.match_id || "match"}-${index}`}>
                                <div className="match-left">
                                    <img className="match-hero-large" src={heroImage} alt={heroLabel} />

                                    <div className="match-main">
                                        <div className="match-line-top">
                                            <span className={`match-result-pill ${isWin ? "win" : "loss"}`}>
                                                {isWin ? "W" : "L"}
                                            </span>
                                            {match.level > 0 ? <span className="match-level">{match.level}</span> : null}
                                            <span className="match-mode-chip">{match.game_mode_label || "Unknown"}</span>
                                        </div>

                                        <div className="match-kda-row">
                                            <span className="match-kda">
                                                {match.kills}/{match.deaths}/{match.assists}
                                            </span>
                                            <span className={`match-impact ${isWin ? "win" : "loss"}`}>
                                                {formatImpact(match.kda_impact)}
                                            </span>
                                        </div>

                                        <div className="match-date-row">
                                            <span>{match.match_date || "-"}</span>
                                        </div>
                                    </div>
                                </div>

                                <div className="match-items-row">
                                    {displayItems.map((item, itemIndex) => (
                                        <div
                                            key={`${match.match_id || "match"}-item-${item.id || itemIndex}`}
                                            className={`match-item ${item.is_neutral ? "neutral" : ""} ${item.is_empty ? "empty" : ""}`}
                                            title={item.name || "Item"}
                                        >
                                            {item.image ? (
                                                <img
                                                    src={item.image}
                                                    alt={item.name || "Item"}
                                                    onError={(event) => {
                                                        const itemSlug = String(item.slug || "")
                                                            .trim()
                                                            .toLowerCase();
                                                        const rawName = String(item.name || "")
                                                            .trim()
                                                            .toLowerCase();
                                                        const nameBasedSlug = rawName
                                                            .replace(/^item\s+\d+$/, "")
                                                            .replace(/[^\w]+/g, "_")
                                                            .replace(/^_+|_+$/g, "");
                                                        const slug = itemSlug || nameBasedSlug;
                                                        if (slug && event.currentTarget.dataset.retry !== "1") {
                                                            event.currentTarget.dataset.retry = "1";
                                                            event.currentTarget.src = `https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/${slug}.png`;
                                                            return;
                                                        }
                                                        event.currentTarget.style.display = "none";
                                                    }}
                                                />
                                            ) : null}
                                        </div>
                                    ))}
                                </div>

                                <div className="match-right">
                                    <span className="match-duration">{match.duration_label || "--:--"}</span>
                                    <span className="match-ago">{match.time_ago || "-"}</span>
                                </div>
                            </div>
                        );
                    })}
                </div>
            ) : (
                <p className="panel-placeholder">Matches will appear after player search</p>
            )}
        </article>
    );
}

window.MatchesTable = MatchesTable;
