function ActivityPanel({ activity }) {
    if (!activity || !Array.isArray(activity.cells)) {
        return null;
    }

    const tone = String(activity.status_tone || "low").toLowerCase();
    const toneClass = tone === "high" ? "high" : tone === "medium" ? "medium" : "low";
    const matchesPerWeek = Number.isFinite(Number(activity.matches_per_week)) ? Number(activity.matches_per_week) : 0;

    return (
        <div className="panel activity-panel">
            <div className="activity-header">
                <h3>{"\u0418\u0433\u0440\u043E\u0432\u0430\u044F \u0430\u043A\u0442\u0438\u0432\u043D\u043E\u0441\u0442\u044C"}</h3>
                <div className="activity-stats-row">
                    <span className={`activity-status-label ${toneClass}`}>{activity.label || "-"}</span>
                    <span className="activity-separator">|</span>
                    <span className="activity-match-count">
                        {activity.total_matches || 0} {"\u043C\u0430\u0442\u0447\u0435\u0439 \u0437\u0430"} {activity.window_days || 365} {"\u0434\u043D\u0435\u0439"}
                    </span>
                    <span className="activity-separator">|</span>
                    <span className="activity-match-count">
                        {matchesPerWeek.toFixed(1)} {"\u0438\u0433\u0440/\u043D\u0435\u0434\u0435\u043B\u044E"}
                    </span>
                </div>
            </div>

            <div className="activity-heatmap-container">
                <div className="activity-months">
                    {Array.isArray(activity.months)
                        ? activity.months.map((month, idx) => (
                              <span key={`month-${idx}`} style={{ gridColumn: month.week + 1 }}>
                                  {month.label}
                              </span>
                          ))
                        : null}
                </div>

                <div className="activity-grid" style={{ gridTemplateColumns: `repeat(${activity.weeks || 53}, 1fr)` }}>
                    {activity.cells.map((cell, index) => (
                        <div
                            key={`cell-${index}`}
                            className={`activity-cell intensity-${cell.intensity}`}
                            title={`${cell.date}: ${cell.count}`}
                            style={{
                                gridColumn: cell.week + 1,
                                gridRow: cell.weekday + 1,
                            }}
                        />
                    ))}
                </div>
            </div>
        </div>
    );
}

window.ActivityPanel = ActivityPanel;
