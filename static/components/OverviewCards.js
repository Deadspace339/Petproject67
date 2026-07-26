function OverviewCards({ data }) {
    const cards = [
        {
            label: "Показатель побед за последнее время",
            value: data ? `${data.recent_wr}%` : "-",
            accent: "red",
        },
        {
            label: "Средний KDA",
            value: data ? data.avg_kda : "-",
            accent: "none",
        },
        {
            label: "Общая ценность",
            value: data ? `${data.avg_gpm} GPM / ${data.avg_xpm} XPM` : "-",
            accent: "none",
        },
    ];

    return (
        <section className="overview-cards">
            {cards.map((card) => (
                <article className="overview-card panel" key={card.label}>
                    <span className="overview-label">{card.label}</span>
                    <strong className={`overview-value ${card.accent === "red" ? "accent-red" : ""}`}>
                        {card.value}
                    </strong>
                </article>
            ))}
        </section>
    );
}

window.OverviewCards = OverviewCards;
