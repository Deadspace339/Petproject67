// Внутренние имена героев в API не совпадают с игровыми: Dota хранит часть
// героев под старыми названиями (nevermore = Shadow Fiend). Простой replace("_")
// давал бы "Nevermore" и "Windrunner", поэтому исключения перечислены явно.
(function () {
    var DISPLAY_NAMES = {
        abyssal_underlord: "Underlord",
        antimage: "Anti-Mage",
        arc_warden: "Arc Warden",
        bounty_hunter: "Bounty Hunter",
        centaur: "Centaur Warrunner",
        doom_bringer: "Doom",
        drow_ranger: "Drow Ranger",
        furion: "Nature's Prophet",
        life_stealer: "Lifestealer",
        magnataur: "Magnus",
        necrolyte: "Necrophos",
        nevermore: "Shadow Fiend",
        obsidian_destroyer: "Outworld Destroyer",
        queenofpain: "Queen of Pain",
        rattletrap: "Clockwerk",
        shredder: "Timbersaw",
        skeleton_king: "Wraith King",
        treant: "Treant Protector",
        wisp: "Io",
        zuus: "Zeus",
    };

    function prettyHeroName(rawName) {
        var slug = String(rawName || "").trim().toLowerCase();
        if (!slug || slug === "unknown") {
            return "Неизвестный герой";
        }
        if (DISPLAY_NAMES[slug]) {
            return DISPLAY_NAMES[slug];
        }
        return slug
            .split("_")
            .filter(Boolean)
            .map(function (part) {
                return part.charAt(0).toUpperCase() + part.slice(1);
            })
            .join(" ");
    }

    window.prettyHeroName = prettyHeroName;
})();
