function AICoachPanel(props) {
    var playerData = props.playerData;
    var activeStats = props.activeStats;
    var selectedWindow = props.selectedWindow;

    var defaultGreeting = "\u042F AI Coach. \u041D\u0430\u0436\u043C\u0438\u0442\u0435 \u043A\u043D\u043E\u043F\u043A\u0443, \u0438 \u044F \u0434\u0430\u043C \u0441\u043E\u0432\u0435\u0442\u044B \u043F\u043E \u043C\u0430\u043A\u0440\u043E, \u043C\u0438\u043A\u0440\u043E \u0438 \u0441\u0431\u043E\u0440\u043A\u0430\u043C.";
    var STORAGE_PREFIX = "coach_chat_v1_";

    // account_id, \u0430 \u043D\u0435 \u043D\u0438\u043A: \u043D\u0438\u043A \u0438 \u0440\u0430\u043D\u0433 \u043C\u0435\u043D\u044F\u044E\u0442\u0441\u044F, \u0438 \u043F\u0435\u0440\u0435\u043F\u0438\u0441\u043A\u0430 \u0442\u043E\u0433\u0434\u0430 \u00AB\u043F\u0435\u0440\u0435\u0435\u0437\u0436\u0430\u043B\u0430\u00BB \u0431\u044B
    // \u043D\u0430 \u0447\u0443\u0436\u043E\u0439 \u043F\u0440\u043E\u0444\u0438\u043B\u044C \u043B\u0438\u0431\u043E \u0442\u0435\u0440\u044F\u043B\u0430\u0441\u044C \u043D\u0430 \u0441\u0432\u043E\u0451\u043C.
    var accountId = playerData && playerData.account_id ? String(playerData.account_id) : "";

    function greetingChat(id) {
        return { accountId: id, messages: [{ role: "assistant", content: defaultGreeting, source: "local" }], actionLog: [] };
    }

    function readStoredChat(id) {
        if (!id) return null;
        try {
            var raw = window.localStorage.getItem(STORAGE_PREFIX + id);
            if (!raw) return null;
            var parsed = JSON.parse(raw);
            if (!parsed || !Array.isArray(parsed.messages) || parsed.messages.length === 0) return null;
            return { accountId: id, messages: parsed.messages, actionLog: Array.isArray(parsed.actionLog) ? parsed.actionLog : [] };
        } catch (error) {
            return null;
        }
    }

    // \u041F\u0435\u0440\u0435\u043F\u0438\u0441\u043A\u0430 \u0436\u0438\u0432\u0451\u0442 \u043E\u0434\u043D\u0438\u043C \u043E\u0431\u044A\u0435\u043A\u0442\u043E\u043C \u0432\u043C\u0435\u0441\u0442\u0435 \u0441 accountId, \u043A\u043E\u0442\u043E\u0440\u043E\u043C\u0443 \u043F\u0440\u0438\u043D\u0430\u0434\u043B\u0435\u0436\u0438\u0442.
    // \u0418\u043D\u0430\u0447\u0435 \u044D\u0444\u0444\u0435\u043A\u0442 \u0441\u043E\u0445\u0440\u0430\u043D\u0435\u043D\u0438\u044F \u043F\u043E\u0441\u043B\u0435 \u0441\u043C\u0435\u043D\u044B \u043F\u0440\u043E\u0444\u0438\u043B\u044F \u0443\u0441\u043F\u0435\u0432\u0430\u043B \u0437\u0430\u043F\u0438\u0441\u0430\u0442\u044C \u0441\u0442\u0430\u0440\u044B\u0435
    // \u0441\u043E\u043E\u0431\u0449\u0435\u043D\u0438\u044F \u0432 \u044F\u0447\u0435\u0439\u043A\u0443 \u043D\u043E\u0432\u043E\u0433\u043E \u0430\u043A\u043A\u0430\u0443\u043D\u0442\u0430 - \u0438\u043C\u0435\u043D\u043D\u043E \u0442\u0430\u043A \u0438\u0441\u0442\u043E\u0440\u0438\u044F \u0438 \u00AB\u043F\u0440\u043E\u0442\u0435\u043A\u0430\u043B\u0430\u00BB.
    var _chat = React.useState(greetingChat(""));
    var chat = _chat[0];
    var setChat = _chat[1];
    var messages = chat.messages;
    var actionLog = chat.actionLog;

    var _st3 = React.useState("");
    var inputValue = _st3[0];
    var setInputValue = _st3[1];

    var _st4 = React.useState(false);
    var loading = _st4[0];
    var setLoading = _st4[1];

    var _st6 = React.useState(false);
    var historyOpen = _st6[0];
    var setHistoryOpen = _st6[1];

    var chatFeedRef = React.useRef(null);
    var hasData = Boolean(playerData && activeStats);

    // === Unicode decode - братский фикс ===
    function decodeUnicode(str) {
        if (!str) return "";
        return String(str).replace(/\\u([0-9a-fA-F]{4})/g, function(match, hex) {
            return String.fromCharCode(parseInt(hex, 16));
        });
    }

    // === ПРОСТОЙ Markdown рендерер (без зависаний) ===
    function renderMd(text) {
        if (!text) return text;
        // Сначала декодируем unicode
        text = decodeUnicode(text);
        var lines = text.split('\n');
        var out = [];
        var items = [];
        var inList = false;
        var ki = 0;
        for (var i = 0; i < lines.length; i++) {
            var line = lines[i];
            var trimmed = line.trim();
            var lm = trimmed.match(/^[-*]\s+(.+)/);
            if (lm) {
                inList = true;
                items.push(lm[1]);
                continue;
            }
            if (inList) {
                var listChildren = items.map(function(it, j) {
                    return React.createElement('li', { key: j }, renderInline(it));
                });
                out.push(React.createElement('ul', { key: 'ul' + ki++ }, listChildren));
                items = [];
                inList = false;
            }
            if (trimmed === '') {
                out.push(React.createElement('br', { key: 'br' + ki++ }));
                continue;
            }
            out.push(React.createElement('div', { key: 'd' + ki++ }, renderInline(line)));
        }
        if (inList) {
            var listChildren2 = items.map(function(it, j) {
                return React.createElement('li', { key: j }, renderInline(it));
            });
            out.push(React.createElement('ul', { key: 'ul' + ki++ }, listChildren2));
        }
        return out.length ? out : text;
    }

    function renderInline(text) {
        var parts = [];
        var remaining = String(text || '');
        var idx = 0;
        var safety = 0;
        while (remaining.length > 0 && safety < 5000) {
            safety++;
            // Bold: **text**
            var bm = remaining.match(/\*\*(.+?)\*\*/);
            if (bm && bm.index === 0) {
                parts.push(React.createElement('strong', { key: idx++ }, bm[1]));
                remaining = remaining.slice(bm[0].length);
                continue;
            }
            // Code: `text`
            var cm = remaining.match(/`(.+?)`/);
            if (cm && cm.index === 0) {
                parts.push(React.createElement('code', { key: idx++, className: 'ai-code' }, cm[1]));
                remaining = remaining.slice(cm[0].length);
                continue;
            }
            // Просто текст до следующего спецсимвола
            var ns = remaining.search(/[\*\*`]/);
            var end = ns > 0 ? ns : remaining.length;
            if (end > 0) {
                parts.push(React.createElement('span', { key: idx++ }, remaining.slice(0, end)));
            }
            remaining = remaining.slice(end > 0 ? end : remaining.length);
            if (end === 0) break; // защита от бесконечного цикла
        }
        return parts.length ? parts : text;
    }

    // snapshot
    var snapshot = React.useMemo(function() {
        if (!hasData) return {};
        var matches = Array.isArray(playerData.matches)
            ? playerData.matches.slice(0, 5).map(function(m) {
                return {
                    hero_name: m.hero_name, game_mode_label: m.game_mode_label,
                    kills: m.kills, deaths: m.deaths, assists: m.assists,
                    duration_label: m.duration_label, match_date: m.match_date,
                    time_ago: m.time_ago,
                    items: Array.isArray(m.items) ? m.items.map(function(it) { return it.name; }) : []
                };
            }) : [];
        return {
            player_name: playerData.name, rank: playerData.rank,
            total_matches: playerData.total_matches, total_wr: playerData.total_wr,
            wins: playerData.wins, losses: playerData.losses,
            turbo_stats: playerData.turbo_stats || {}, selected_window: selectedWindow,
            recent_wr: activeStats.recent_wr, avg_kda: activeStats.avg_kda,
            avg_kills: activeStats.avg_kills, avg_deaths: activeStats.avg_deaths,
            avg_assists: activeStats.avg_assists, avg_gpm: activeStats.avg_gpm,
            avg_xpm: activeStats.avg_xpm, party_rate: activeStats.party_rate,
            solo_rate: activeStats.solo_rate, lane_record: activeStats.lane_record || {},
            lane_breakdown: activeStats.lane_breakdown || [], best_lane: activeStats.best_lane || null,
            top_heroes: activeStats.top_heroes || [],
            most_played_heroes: playerData.most_played_heroes || [],
            meta_guides: playerData.meta_guides || [],
            win_trend: activeStats.win_trend || [],
            trend_points: activeStats.trend_points || [],
            radar_data: activeStats.radar_data || [], activity: playerData.activity || null, matches: matches
        };
    }, [playerData, activeStats, selectedWindow, hasData]);

    var presetPrompts = [
        { id: "last_match_review", text: "\u0420\u0430\u0437\u0431\u0435\u0440\u0438 \u043F\u043E\u0441\u043B\u0435\u0434\u043D\u044E\u044E \u0438\u0433\u0440\u0443 \u0438 \u0434\u0430\u0439 5 \u0442\u043E\u0447\u0435\u0447\u043D\u044B\u0445 \u0443\u043B\u0443\u0447\u0448\u0435\u043D\u0438\u0439" },
        { id: "full_analytics", text: "\u0414\u0430\u0439 \u043F\u043E\u043B\u043D\u0443\u044E \u0430\u043D\u0430\u043B\u0438\u0442\u0438\u043A\u0443: \u043C\u0430\u043A\u0440\u043E, \u043C\u0438\u043A\u0440\u043E \u0438 \u0441\u0442\u0430\u0431\u0438\u043B\u044C\u043D\u043E\u0441\u0442\u044C" },
        { id: "weakness_plan", text: "\u041F\u043E\u043A\u0430\u0436\u0438 \u0441\u043B\u0430\u0431\u044B\u0435 \u0441\u0442\u043E\u0440\u043E\u043D\u044B (\u043C\u0430\u043A\u0440\u043E/\u043C\u0438\u043A\u0440\u043E) \u0438 \u043F\u043B\u0430\u043D \u0438\u0441\u043F\u0440\u0430\u0432\u043B\u0435\u043D\u0438\u044F" },
        { id: "best_role_focus", text: "\u041A\u0430\u043A\u0430\u044F \u0443 \u043C\u0435\u043D\u044F \u043B\u0443\u0447\u0448\u0430\u044F \u043F\u043E\u0437\u0438\u0446\u0438\u044F \u0438 \u0433\u0434\u0435 \u0444\u043E\u043A\u0443\u0441\u0438\u0440\u043E\u0432\u0430\u0442\u044C\u0441\u044F" },
        { id: "meta_main", text: "\u041F\u043E\u0434\u0441\u043A\u0430\u0436\u0438 \u0433\u0435\u0440\u043E\u0435\u0432 \u043C\u0435\u0442\u044B \u0438 \u043A\u043E\u0433\u043E \u043B\u0443\u0447\u0448\u0435 \u043C\u0435\u0439\u043D\u0438\u0442\u044C" }
    ];

    function inferPromptIdFromText(text) {
        var lower = String(text || "").toLowerCase();
        if (lower.indexOf("\u043F\u043E\u0441\u043B") >= 0 || lower.indexOf("last") >= 0) return "last_match_review";
        if (lower.indexOf("\u0441\u043B") >= 0 || lower.indexOf("\u0438\u0441\u043F") >= 0) return "weakness_plan";
        if (lower.indexOf("\u043F\u043E\u0437") >= 0 || lower.indexOf("lane") >= 0) return "best_role_focus";
        if (lower.indexOf("\u043C\u0435\u0442") >= 0 || lower.indexOf("\u043C\u0435\u0439\u043D") >= 0) return "meta_main";
        return "full_analytics";
    }

    function buildActionSummary(events) {
        var safe = Array.isArray(events) ? events : [];
        var usage = presetPrompts.map(function(p) {
            return {
                prompt_id: p.id, label: p.text,
                count: safe.reduce(function(a, e) { return a + (e.prompt_id === p.id ? 1 : 0); }, 0)
            };
        });
        var top = usage.reduce(function(b, r) { return r.count > b.count ? r : b; }, { prompt_id: "", label: "", count: 0 });
        return { total_actions: safe.length, preset_usage: usage, top_preset_id: top.count > 0 ? top.prompt_id : "", top_preset_label: top.count > 0 ? top.label : "", recent_actions: safe.slice(-5) };
    }

    React.useEffect(function() {
        if (chatFeedRef.current) chatFeedRef.current.scrollTop = chatFeedRef.current.scrollHeight;
    }, [messages, loading]);

    // Смена профиля: подставляем переписку именно этого аккаунта.
    React.useEffect(function() {
        if (chat.accountId === accountId) return;
        setChat(readStoredChat(accountId) || greetingChat(accountId));
        setInputValue("");
        setLoading(false);
        setHistoryOpen(false);
    }, [accountId, chat.accountId]);

    // Сохраняем только когда состояние и профиль совпадают - иначе на первом
    // кадре после переключения в ячейку нового аккаунта уехала бы чужая история.
    React.useEffect(function() {
        if (!chat.accountId || chat.accountId !== accountId) return;
        try {
            window.localStorage.setItem(
                STORAGE_PREFIX + chat.accountId,
                JSON.stringify({ messages: chat.messages.slice(-40), actionLog: chat.actionLog.slice(-25) })
            );
        } catch (error) {
            /* приватный режим или переполненное хранилище - переписка просто не переживёт перезагрузку */
        }
    }, [accountId, chat]);

    function appendMessages(newMessages) {
        setChat(function(prev) {
            return { accountId: prev.accountId, messages: prev.messages.concat(newMessages), actionLog: prev.actionLog };
        });
    }

    function clearChat() {
        if (accountId) {
            try {
                window.localStorage.removeItem(STORAGE_PREFIX + accountId);
            } catch (error) {
                /* нечего чистить */
            }
        }
        setChat(greetingChat(accountId));
        setInputValue("");
        setHistoryOpen(false);
    }

    // История запросов: последние вопросы этого аккаунта, свежие сверху, без повторов.
    var promptHistory = [];
    var seenPrompts = {};
    for (var hi = actionLog.length - 1; hi >= 0; hi--) {
        var entry = actionLog[hi];
        var text = entry && entry.prompt_preview ? String(entry.prompt_preview) : "";
        if (!text || seenPrompts[text]) continue;
        seenPrompts[text] = true;
        promptHistory.push(entry);
        if (promptHistory.length >= 8) break;
    }

    var sendPrompt = async function(prompt, options) {
        options = options || {};
        var promptText = String(prompt || "").trim();
        if (!promptText || loading) return;
        var promptId = String(options.promptId || "").trim();
        var origin = String(options.origin || (promptId ? "preset" : "user_text"));
        var resolvedId = promptId || (origin === "preset" ? inferPromptIdFromText(promptText) : "");
        if (!hasData && origin === "preset") {
            appendMessages([{ role: "assistant", content: "\u0421\u043D\u0430\u0447\u0430\u043B\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u0435 \u043F\u0440\u043E\u0444\u0438\u043B\u044C.", source: "local" }]);
            return;
        }
        var userMsg = { role: "user", content: promptText };
        var allMsgs = messages.concat([userMsg]).slice(-12);
        var conv = allMsgs.map(function(m) {
            return { role: m.role === "assistant" ? "assistant" : "user", content: String(m.content || "").slice(0, 1000) };
        }).filter(function(m) { return m.content; });
        var nextAction = { timestamp: new Date().toISOString(), origin: origin, prompt_id: resolvedId, prompt_preview: promptText.slice(0, 120) };
        var nextLog = actionLog.concat([nextAction]).slice(-25);
        setChat(function(prev) {
            return { accountId: prev.accountId, messages: prev.messages.concat([userMsg]), actionLog: nextLog };
        });
        setInputValue("");
        setLoading(true);
        try {
            var resp = await fetch("/api/coach", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    prompt: promptText,
                    snapshot: snapshot,
                    selected_prompt_id: resolvedId,
                    prompt_origin: origin,
                    conversation: conv,
                    action_summary: buildActionSummary(nextLog)
                })
            });
            var data = null;
            try { data = await resp.json(); } catch(e) { data = null; }
            var answer = (data && data.answer) ? data.answer : (data && data.error) ? data.error : "\u041D\u0435 \u0443\u0434\u0430\u043B\u043E\u0441\u044C \u043F\u043E\u043B\u0443\u0447\u0438\u0442\u044C \u043E\u0442\u0432\u0435\u0442.";
            var source = (data && data.source) ? data.source : "local";
            appendMessages([{ role: "assistant", content: answer, source: source }]);
        } catch(e) {
            appendMessages([{ role: "assistant", content: "\u041E\u0448\u0438\u0431\u043A\u0430 \u0441\u0432\u044F\u0437\u0438 \u0441 AI Coach.", source: "local" }]);
        } finally {
            setLoading(false);
        }
    };

    return React.createElement('article', { className: 'panel ai-coach-panel' },
        React.createElement('div', { className: 'panel-title-row' },
            React.createElement('h3', null, 'AI Coach'),
            React.createElement('div', { className: 'ai-toolbar' },
                React.createElement('span', { className: 'panel-subtitle' },
                    hasData ? "\u0413\u043E\u0442\u043E\u0432 \u043A \u0430\u043D\u0430\u043B\u0438\u0437\u0443" : "\u041E\u0436\u0438\u0434\u0430\u044E \u0434\u0430\u043D\u043D\u044B\u0435"
                ),
                React.createElement('button', {
                    className: 'ai-tool-btn' + (historyOpen ? ' is-active' : ''),
                    onClick: function() { setHistoryOpen(!historyOpen); },
                    disabled: promptHistory.length === 0,
                    title: promptHistory.length ? "\u0418\u0441\u0442\u043E\u0440\u0438\u044F \u0437\u0430\u043F\u0440\u043E\u0441\u043E\u0432" : "\u0417\u0430\u043F\u0440\u043E\u0441\u043E\u0432 \u0435\u0449\u0451 \u043D\u0435 \u0431\u044B\u043B\u043E"
                }, "\u0418\u0441\u0442\u043E\u0440\u0438\u044F" + (promptHistory.length ? " (" + promptHistory.length + ")" : "")),
                React.createElement('button', {
                    className: 'ai-tool-btn danger',
                    onClick: clearChat,
                    disabled: loading || messages.length <= 1,
                    title: "\u041E\u0447\u0438\u0441\u0442\u0438\u0442\u044C \u043F\u0435\u0440\u0435\u043F\u0438\u0441\u043A\u0443 \u0441 \u044D\u0442\u0438\u043C \u043F\u0440\u043E\u0444\u0438\u043B\u0435\u043C"
                }, "\u041E\u0447\u0438\u0441\u0442\u0438\u0442\u044C")
            )
        ),

        historyOpen && promptHistory.length > 0
            ? React.createElement('div', { className: 'ai-history' },
                React.createElement('p', { className: 'ai-history-title' }, "\u041F\u0440\u043E\u0448\u043B\u044B\u0435 \u0437\u0430\u043F\u0440\u043E\u0441\u044B \u043F\u043E \u044D\u0442\u043E\u043C\u0443 \u043F\u0440\u043E\u0444\u0438\u043B\u044E"),
                promptHistory.map(function(entry, index) {
                    var when = "";
                    try {
                        when = new Date(entry.timestamp).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
                    } catch (error) {
                        when = "";
                    }
                    return React.createElement('button', {
                        key: 'hist-' + index,
                        className: 'ai-history-item',
                        disabled: loading,
                        onClick: function() { sendPrompt(entry.prompt_preview, { promptId: entry.prompt_id, origin: "history" }); }
                    },
                        React.createElement('span', { className: 'ai-history-text' }, entry.prompt_preview),
                        when ? React.createElement('span', { className: 'ai-history-time' }, when) : null
                    );
                })
            )
            : null,
        React.createElement('div', { className: 'ai-prompt-grid' },
            presetPrompts.map(function(preset) {
                return React.createElement('button', {
                    key: preset.id,
                    className: 'ai-prompt-btn',
                    onClick: function() { sendPrompt(preset.text, { promptId: preset.id, origin: "preset" }); },
                    disabled: loading || !hasData
                }, preset.text);
            })
        ),
        React.createElement('div', { className: 'ai-chat-feed', ref: chatFeedRef },
            messages.map(function(message, index) {
                return React.createElement('div', { key: 'msg-' + index, className: 'ai-msg ' + message.role },
                    React.createElement('div', { className: 'ai-msg-body' },
                        message.role === "assistant" ? renderMd(message.content) : message.content
                    ),
                    message.role === "assistant" ? React.createElement('span', {
                        className: 'ai-msg-source ' + (message.source === "local" ? "local" : "llm")
                    }, message.source === "gemini" ? "Gemini" : message.source === "llm" ? "LLM" : "Local AI") : null
                );
            }),
            loading ? React.createElement('div', { className: 'ai-loading' }, "AI Coach \u0430\u043D\u0430\u043B\u0438\u0437\u0438\u0440\u0443\u0435\u0442...") : null
        ),
        React.createElement('div', { className: 'ai-input-row' },
            React.createElement('input', {
                type: 'text',
                value: inputValue,
                onChange: function(e) { setInputValue(e.target.value); },
                onKeyDown: function(e) { if (e.key === "Enter") sendPrompt(inputValue, { origin: "user_text" }); },
                className: 'ai-input',
                placeholder: "\u0421\u043F\u0440\u043E\u0441\u0438: \u043A\u0430\u043A \u0443\u043B\u0443\u0447\u0448\u0438\u0442\u044C \u043C\u0430\u043A\u0440\u043E?",
                disabled: loading
            }),
            React.createElement('button', {
                className: 'ai-send-btn',
                onClick: function() { sendPrompt(inputValue, { origin: "user_text" }); },
                disabled: loading || !inputValue.trim()
            }, "\u041E\u0442\u043F\u0440\u0430\u0432\u0438\u0442\u044C")
        )
    );
}

window.AICoachPanel = AICoachPanel;
