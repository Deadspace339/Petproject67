function AppHeader({ playerId, onPlayerIdChange, onSearch, loading, onReset }) {
    return (
        <header className="top-nav panel">
            <div className="brand-block">
                <p className="brand-eyebrow">Dota 2 + CS2 Analytics</p>
                <h1 className="brand-title">
                    <a href="/">
                        Meta<span>Analytics</span>
                    </a>
                </h1>
            </div>

            <div className="search-controls">
                <input
                    type="text"
                    value={playerId}
                    onChange={(event) => onPlayerIdChange(event.target.value)}
                    onKeyDown={(event) => {
                        if (event.key === "Enter") {
                            onSearch();
                        }
                    }}
                    className="search-input"
                    placeholder="Steam ID / profile URL / nickname"
                />
                <button className="search-button" onClick={onSearch} disabled={loading}>
                    {loading ? "\u0417\u0430\u0433\u0440\u0443\u0437\u043A\u0430..." : "\u0410\u043D\u0430\u043B\u0438\u0437"}
                </button>
                <a className="search-link" href="/">
                    {"\u041E \u043F\u0440\u043E\u0435\u043A\u0442\u0435"}
                </a>
            </div>
        </header>
    );
}

window.AppHeader = AppHeader;
