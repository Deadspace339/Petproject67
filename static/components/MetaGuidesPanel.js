function MetaGuidesPanel({ guides }) {
    const GUIDE_LIMIT = 5;
    const blockedAuthors = new Set(["greayshark"]);
    const heroImageAliases = {
        shadow_fiend: "nevermore",
        shadow: "nevermore",
    };

    const fallbackGuides = [
        {
            hero_name: "phantom_assassin",
            title: "PA Carry Snowball",
            author: "Torte de Lini",
            likes: 56072,
            games: 365902,
        },
        {
            hero_name: "nevermore",
            title: "SF Mid Tempo (Meta 7.39)",
            author: "ImmortalFaith",
            likes: 68291,
            games: 402113,
        },
        {
            hero_name: "invoker",
            title: "Invoker Quas Exort",
            author: "Torte de Lini",
            likes: 59224,
            games: 331005,
        },
        {
            hero_name: "lion",
            title: "Lion Support Punish",
            author: "ImmortalFaith",
            likes: 47320,
            games: 286411,
        },
        {
            hero_name: "juggernaut",
            title: "Juggernaut Safe Lane Core",
            author: "DATOHLEONG",
            likes: 44815,
            games: 279540,
        },
        {
            hero_name: "axe",
            title: "Axe Blink Pressure",
            author: "ImmortalFaith",
            likes: 42951,
            games: 244810,
        },
        {
            hero_name: "tiny",
            title: "Tiny Mid Roamer",
            author: "ImmortalFaith",
            likes: 41274,
            games: 227411,
        },
        {
            hero_name: "mars",
            title: "Mars Offlane Initiation",
            author: "DATOHLEONG",
            likes: 38954,
            games: 210882,
        },
    ];

    const normalizeGuide = (guide) => {
        const rawHeroName = String(guide?.hero_name || "unknown").trim().toLowerCase() || "unknown";
        const heroName = heroImageAliases[rawHeroName] || rawHeroName;
        const title = String(guide?.title || "Meta Guide").trim();
        const author = String(guide?.author || "Unknown").trim();
        const likes = Number(guide?.likes || 0);
        const games = Number(guide?.games || 0);
        const providedHeroImage = String(guide?.hero_image || "").trim();
        const normalizedProvided = providedHeroImage
            ? providedHeroImage.replace(/\/heroes\/(shadow_fiend|shadow)\.png$/i, "/heroes/nevermore.png")
            : "";
        const heroImage =
            normalizedProvided ||
            `https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/${heroName}.png`;

        return {
            hero_name: heroName,
            title,
            author,
            likes: Number.isFinite(likes) ? likes : 0,
            games: Number.isFinite(games) ? games : 0,
            hero_image: heroImage,
        };
    };

    const incoming = Array.isArray(guides) ? guides : [];
    const safeIncoming = incoming
        .map(normalizeGuide)
        .filter((guide) => !blockedAuthors.has(guide.author.toLowerCase()));
    const usingServerGuides = safeIncoming.length > 0;
    const pool = usingServerGuides ? safeIncoming : fallbackGuides.map(normalizeGuide);
    const merged = [...pool];

    if (merged.length < GUIDE_LIMIT) {
        const used = new Set(merged.map((guide) => `${guide.hero_name}|${guide.title}|${guide.author}`));
        for (const guide of fallbackGuides.map(normalizeGuide)) {
            const key = `${guide.hero_name}|${guide.title}|${guide.author}`;
            if (used.has(key) || blockedAuthors.has(guide.author.toLowerCase())) {
                continue;
            }
            used.add(key);
            merged.push(guide);
            if (merged.length >= GUIDE_LIMIT) {
                break;
            }
        }
    }

    if (!usingServerGuides) {
        merged.sort((left, right) => {
            if (right.likes !== left.likes) {
                return right.likes - left.likes;
            }
            return right.games - left.games;
        });
    }

    const visibleGuides = merged.slice(0, GUIDE_LIMIT);
    const maxLikes = visibleGuides.length > 0 ? Math.max(...visibleGuides.map((guide) => guide.likes || 0), 1) : 1;

    const formatCompact = (value) => {
        const numeric = Number(value || 0);
        if (!Number.isFinite(numeric) || numeric <= 0) {
            return "0";
        }
        if (numeric >= 1_000_000) {
            return `${(numeric / 1_000_000).toFixed(1)}M`;
        }
        if (numeric >= 1_000) {
            return `${(numeric / 1_000).toFixed(1)}K`;
        }
        return `${Math.round(numeric)}`;
    };

    return (
        <article className="panel meta-guides-panel">
            <div className="panel-title-row">
                <h3>{"\u041C\u0435\u0442\u0430-\u0433\u0430\u0439\u0434\u044B"}</h3>
                <span className="panel-subtitle">{"\u041F\u043E\u043F\u0443\u043B\u044F\u0440\u043D\u044B\u0435 \u0441\u0431\u043E\u0440\u043A\u0438"}</span>
            </div>

            <div className="meta-guides-list">
                {visibleGuides.map((guide, index) => {
                    const likesWidth = Math.max(8, ((guide.likes || 0) / maxLikes) * 100);
                    const heroLabel = guide.hero_name === "nevermore" ? "shadow fiend" : guide.hero_name.replace(/_/g, " ");

                    return (
                        <div className="meta-guide-row" key={`${guide.hero_name}-${guide.title}-${index}`}>
                            <div className="meta-guide-rank">{index + 1}</div>

                            <div className="meta-guide-main">
                                <img
                                    src={guide.hero_image}
                                    alt={heroLabel}
                                    className="meta-guide-hero"
                                    onError={(event) => {
                                        if (event.currentTarget.dataset.retry === "1") {
                                            event.currentTarget.style.visibility = "hidden";
                                            return;
                                        }
                                        event.currentTarget.dataset.retry = "1";
                                        const fallbackHero = heroImageAliases[guide.hero_name] || guide.hero_name || "unknown";
                                        event.currentTarget.src = `https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/${fallbackHero}.png`;
                                    }}
                                />
                                <div className="meta-guide-text">
                                    <strong>{guide.title}</strong>
                                    <span>
                                        {guide.author} - {heroLabel}
                                    </span>
                                </div>
                            </div>

                            <div className="meta-guide-stats">
                                <div className="meta-guide-numbers">
                                    <span>{"\u041B\u0430\u0439\u043A\u0438"}: {formatCompact(guide.likes)}</span>
                                    <span>{"\u041C\u0430\u0442\u0447\u0438"}: {formatCompact(guide.games)}</span>
                                </div>
                                <div className="meta-guide-track">
                                    <div className="meta-guide-fill" style={{ width: `${likesWidth}%` }} />
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </article>
    );
}

window.MetaGuidesPanel = MetaGuidesPanel;
