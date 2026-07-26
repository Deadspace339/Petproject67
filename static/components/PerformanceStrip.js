function PerformanceStrip({ data }) {
    const totalMatches = data ? data.total_matches.toLocaleString() : "0";
    const firstMatch = data ? data.first_match : "-";
    const totalWr = data ? data.total_wr : 0;
    const wins = data ? data.wins.toLocaleString() : "0";
    const losses = data ? data.losses.toLocaleString() : "0";

    return (
        <section className="performance-strip">
            <article className="strip-card panel">
                <div className="strip-head">
                    <span className="strip-highlight gold">{totalMatches} Матчей</span>
                    <span className="strip-dim">Первый матч: {firstMatch}</span>
                </div>
                <div className="tick-row">
                    {(data && data.win_trend ? data.win_trend.slice(-56) : []).map((r, i) => (<div key={i} className={`match-tick ${r>0?"tick-win":"tick-loss"}`} title={r>0?"W":"L"}/>)) || Array.from({length:56}).map((_,i)=><div className="match-tick" key={i}/>)}
                </div>
            </article>

            <article className="strip-card panel">
                <div className="strip-head">
                    <span className="strip-highlight green">{totalWr}% Процент побед</span>
                    <span className="strip-dim">
                        <span className="wins-count">{wins}</span> - <span className="losses-count">{losses}</span>
                    </span>
                </div>
                <div className="wr-progress-bg">
                    <div className="wr-progress-fill" style={{ width: `${totalWr}%` }} />
                </div>
            </article>
        </section>
    );
}

window.PerformanceStrip = PerformanceStrip;
