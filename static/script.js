if (!window.React || !window.ReactDOM) {
    const root = document.getElementById("root");
    if (root) {
        root.innerHTML = `
            <div class="panel error-panel">
                Не удалось загрузить React/ReactDOM с CDN. Проверьте интернет или блокировки CDN.
            </div>
        `;
    }
    throw new Error("React or ReactDOM is not available");
}

const { useEffect, useMemo, useState } = React;

class DashboardErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, message: "" };
    }

    static getDerivedStateFromError(error) {
        return {
            hasError: true,
            message: error && error.message ? String(error.message) : "Неизвестная ошибка интерфейса",
        };
    }

    componentDidCatch(error) {
        console.error("Dashboard render error:", error);
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="panel error-panel">
                    Ошибка интерфейса: {this.state.message}. Обновите страницу. Если ошибка повторится, компонент уже не
                    сломает весь дашборд молча.
                </div>
            );
        }
        return this.props.children;
    }
}

function App() {
    const [playerId, setPlayerId] = useState("");
    const [playerData, setPlayerData] = useState(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [selectedWindow, setSelectedWindow] = useState(25);

    const analyze = async (rawId = playerId) => {
        const normalizedInput = String(rawId ?? "").trim();
        if (!normalizedInput) {
            setError("Введите Steam ID, ссылку профиля или ник");
            setPlayerData(null);
            return;
        }

        setPlayerId(normalizedInput);
        localStorage.setItem("dota_query", normalizedInput);

        setLoading(true);
        setError("");

        try {
            // Add timeout to fetch requests
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout

            const resolveResponse = await fetch(`/api/player/resolve?query=${encodeURIComponent(normalizedInput)}`, {
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            
            const resolved = await resolveResponse.json();

            if (!resolveResponse.ok || resolved.error || !resolved.account_id) {
                setPlayerData(null);
                setError(resolved.error || "Не удалось найти игрока по введенным данным");
                return;
            }

            const resolvedId = String(resolved.account_id);
            localStorage.setItem("dota_id", resolvedId);

            // Second fetch with timeout
            const controller2 = new AbortController();
            const timeoutId2 = setTimeout(() => controller2.abort(), 45000); // 45 second timeout

            const response = await fetch(`/api/player/${resolvedId}`, {
                signal: controller2.signal
            });
            clearTimeout(timeoutId2);
            
            const data = await response.json();

            if (!response.ok || data.error) {
                setPlayerData(null);
                setError(data.error || "Ошибка загрузки данных");
                return;
            }

            setPlayerData(data);
            const has25 = data && data.windows && data.windows["25"] && data.windows["25"].matches > 0;
            const has100 = data && data.windows && data.windows["100"] && data.windows["100"].matches > 0;
            setSelectedWindow(has25 ? 25 : has100 ? 100 : 25);
        } catch (requestError) {
            setPlayerData(null);
            if (requestError.name === 'AbortError') {
                setError("Превышено время ожидания. Попробуйте ещё раз позже.");
            } else {
                setError("Не удалось получить данные. Проверьте соединение и попробуйте снова.");
            }
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        const savedQuery = localStorage.getItem("dota_query") || localStorage.getItem("dota_id");
        if (savedQuery) {
            setPlayerId(savedQuery);
        }
    }, []);

    const activeStats = useMemo(() => {
        if (!playerData || !playerData.windows) {
            return null;
        }

        const selected = playerData.windows[String(selectedWindow)];
        if (selected && selected.matches > 0) {
            return selected;
        }

        return playerData.windows["25"] || playerData.windows["100"] || null;
    }, [playerData, selectedWindow]);
    const hasWindow100 = Boolean(
        playerData &&
            playerData.windows &&
            playerData.windows["100"] &&
            playerData.windows["100"].matches > 0,
    );

    const Header = window.AppHeader;
    const Banner = window.PlayerBanner;
    const Strip = window.PerformanceStrip;
    const Cards = window.OverviewCards;
    const Heroes = window.TopHeroesCard;
    const Matches = window.MatchesTable;
    const MostPlayed = window.MostPlayedHeroesPanel;
    const Allies = window.AlliesPanel;
    const Activity = window.ActivityPanel;
    const Trends = window.TrendsPanel;
    const Coach = window.AICoachPanel;
    const MetaGuides = window.MetaGuidesPanel;

    return (
        <div className="app-shell">
            <Header
                playerId={playerId}
                onPlayerIdChange={setPlayerId}
                onSearch={() => analyze()}
                onReset={() => { setPlayerId(""); setPlayerData(null); setError(""); localStorage.removeItem("dota_query"); localStorage.removeItem("dota_id"); }}
                loading={loading}
            />

            {error ? <div className="panel error-panel">{error}</div> : null}

            <Banner data={playerData} />

            <div className="dashboard-grid">
                <section className="dashboard-main">
                    <Strip data={playerData} />
                    <Trends
                        stats={activeStats}
                        windows={playerData ? playerData.windows : null}
                        selectedWindow={selectedWindow}
                        onWindowChange={setSelectedWindow}
                        hasWindow100={hasWindow100}
                    />
                    <Matches matches={playerData ? playerData.matches : []} />
                </section>

                <aside className="dashboard-side">
                    <Cards data={activeStats} />
                    <Heroes topHeroes={activeStats ? activeStats.top_heroes : []} />
                    <Activity activity={playerData ? playerData.activity : null} />
                    <Coach
                        playerData={playerData}
                        activeStats={activeStats}
                        selectedWindow={selectedWindow}
                    />
                    <MetaGuides guides={playerData ? playerData.meta_guides : []} />
                </aside>
            </div>

            <section className="features-grid">
                <MostPlayed heroes={playerData ? playerData.most_played_heroes : []} />
                <Allies allies={playerData ? playerData.top_allies : []} />
            </section>
        </div>
    );
}

const requiredComponents = [
    "AppHeader",
    "PlayerBanner",
    "PerformanceStrip",
    "OverviewCards",
    "TopHeroesCard",
    "MatchesTable",
    "TrendsPanel",
    "MostPlayedHeroesPanel",
    "AlliesPanel",
    "ActivityPanel",
    "AICoachPanel",
    "MetaGuidesPanel",
];

function findMissingComponents() {
    return requiredComponents.filter((name) => typeof window[name] !== "function");
}

function mountReactApp(retryCount = 0) {
    const missing = findMissingComponents();
    if (missing.length === 0) {
        ReactDOM.createRoot(document.getElementById("root")).render(
            <DashboardErrorBoundary>
                <App />
            </DashboardErrorBoundary>,
        );
        return;
    }

    if (retryCount < 120) {
        setTimeout(() => mountReactApp(retryCount + 1), 50);
        return;
    }

    const root = document.getElementById("root");
    if (root) {
        root.innerHTML = `
            <div class="panel error-panel">
                Ошибка загрузки компонентов интерфейса: ${missing.join(", ")}.
                Проверьте, что файлы доступны в /static/components/.
            </div>
        `;
    }

    console.error("UI components failed to load:", missing);
}

mountReactApp();
