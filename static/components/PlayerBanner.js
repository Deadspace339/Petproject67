function PlayerBanner({ data }) {
    const toRussianRank = (rawRank) => {
        const source = String(rawRank || "").trim();
        if (!source) return "\u0411\u0435\u0437 \u0440\u0430\u043D\u0433\u0430";

        const dictionary = {
            Unranked: "\u0411\u0435\u0437 \u0440\u0430\u043D\u0433\u0430",
            Herald: "\u0420\u0435\u043A\u0440\u0443\u0442",
            Guardian: "\u0421\u0442\u0440\u0430\u0436",
            Crusader: "\u0420\u044B\u0446\u0430\u0440\u044C",
            Archon: "\u0413\u0435\u0440\u043E\u0439",
            Legend: "\u041B\u0435\u0433\u0435\u043D\u0434\u0430",
            Ancient: "\u0412\u043B\u0430\u0441\u0442\u0435\u043B\u0438\u043D",
            Divine: "\u0411\u043E\u0436\u0435\u0441\u0442\u0432\u043E",
            Immortal: "\u0422\u0438\u0442\u0430\u043D",
        };

        let translated = source;
        Object.entries(dictionary).forEach(([en, ru]) => {
            translated = translated.replace(new RegExp(`\\b${en}\\b`, "gi"), ru);
        });

        return translated;
    };

    if (!data) {
        return (
            <section className="hero-banner panel hero-banner-empty">
                <div>
                    <p className="hero-status">{"\u041E\u0436\u0438\u0434\u0430\u043D\u0438\u0435 \u043F\u0440\u043E\u0444\u0438\u043B\u044F"}</p>
                    <h2 className="hero-name">
                        {"\u0412\u0432\u0435\u0434\u0438\u0442\u0435 Steam ID, \u0447\u0442\u043E\u0431\u044B \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044C \u0430\u043D\u0430\u043B\u0438\u0442\u0438\u043A\u0443"}
                    </h2>
                    <p className="hero-subline">
                        {"\u041F\u043E\u0441\u043B\u0435 \u043F\u043E\u0438\u0441\u043A\u0430 \u0437\u0434\u0435\u0441\u044C \u043F\u043E\u044F\u0432\u0438\u0442\u0441\u044F \u043A\u0430\u0440\u0442\u043E\u0447\u043A\u0430 \u0438\u0433\u0440\u043E\u043A\u0430 \u043A\u0430\u043A \u0432 STRATZ-\u0441\u0442\u0438\u043B\u0435."}
                    </p>
                </div>
            </section>
        );
    }

    const rankTier = Number(data.rank_tier || 0);
    const rankMedal = rankTier > 0 ? Math.floor(rankTier / 10) : 0;
    const rankStar = rankTier > 0 ? rankTier % 10 : 0;
    const safeMedal = rankMedal >= 0 && rankMedal <= 8 ? rankMedal : 0;
    const isImmortal = rankMedal === 8;
    const medalImage = isImmortal ? "/static/ranks/medal_8c.png" : `/static/ranks/medal_${safeMedal}.png`;
    const starCount = isImmortal ? 5 : Math.min(Math.max(rankStar, 0), 5);
    const rankLabel = toRussianRank(data.rank);

    return (
        <section className="hero-banner panel">
            <div className="hero-banner-main">
                <img className="hero-avatar" src={data.avatar || "https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/avatars/fe/fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb_full.jpg"} alt={data.name} onError={(e)=>{e.target.src="https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/avatars/fe/fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb_full.jpg"}} />
                <div>
                    <p className="hero-status">{"\u041F\u0440\u043E\u0444\u0438\u043B\u044C \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043D"}</p>
                    <h2 className="hero-name">{data.name}</h2>
                    <p className="hero-subline">
                        {"\u041F\u0440\u043E\u0444\u0438\u043B\u044C: \u043F\u043E\u0441\u043B\u0435\u0434\u043D\u0438\u0435 \u043C\u0430\u0442\u0447\u0438, \u0441\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043A\u0430 \u0438 \u0441\u0438\u0433\u043D\u0430\u043B\u044B \u0444\u043E\u0440\u043C\u044B."}
                    </p>
                </div>
            </div>

            <div className="hero-banner-meta">
                <div className="hero-meta-item">
                    <span>{"\u0420\u0430\u043D\u0433"}</span>
                    <div className="rank-value">
                        <span className="rank-icon-image-wrap" aria-hidden="true">
                            {starCount > 0 ? (
                                <span className="rank-star-row">
                                    {Array.from({ length: starCount }).map((_, index) => (
                                        <img
                                            key={`rank-star-${index}`}
                                            className="rank-star-dot"
                                            src="/static/ranks/star_5.png"
                                            alt=""
                                        />
                                    ))}
                                </span>
                            ) : null}
                            <img className="rank-medal-image" src={medalImage} alt="" />
                        </span>
                        <b className="rank-label">{rankLabel}</b>
                    </div>
                </div>
                <div className="hero-meta-item">
                    <span>{"\u041C\u0430\u0442\u0447\u0435\u0439"}</span>
                    <b>{data.total_matches.toLocaleString()}</b>
                </div>
                <div className="hero-meta-item">
                    <span>{"\u0412\u0438\u043D\u0440\u0435\u0439\u0442"}</span>
                    <b>{data.total_wr}%</b>
                </div>
                <div className="hero-meta-item">
                    <span>{"\u041F\u0435\u0440\u0432\u044B\u0439 \u043C\u0430\u0442\u0447"}</span>
                    <b>{data.first_match}</b>
                </div>
            </div>
        </section>
    );
}

window.PlayerBanner = PlayerBanner;
