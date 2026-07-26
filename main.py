import asyncio
import datetime
import json
import os
import re
import secrets
import urllib.parse
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

import db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Отказ базы не должен мешать старту: init_db сообщает о проблеме и возвращает
    # False, приложение продолжает работать без сохранения данных.
    await db.init_db()
    yield
    await db.close_db()


app = FastAPI(lifespan=lifespan)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
ENV_FILE_PATH = os.path.join(BASE_DIR, ".env")
LOCAL_HEROES_PATH = os.path.join(STATIC_DIR, "data", "heroes.json")
LOCAL_ITEMS_PATH = os.path.join(STATIC_DIR, "data", "items.json")


def load_env_file(env_file_path):
    if not os.path.exists(env_file_path):
        return

    try:
        # utf-8-sig, not utf-8: editors that save .env with a BOM would otherwise
        # turn the first key into "﻿GEMINI_API_KEY" and silently lose it.
        with open(env_file_path, "r", encoding="utf-8-sig") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("\"'")

                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


load_env_file(ENV_FILE_PATH)

SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip() or os.getenv("SECRET_KEY", "").strip()
if not SESSION_SECRET:
    # A shared hard-coded default would let anyone forge a session cookie once the
    # app is public. Fall back to a per-process random key instead: logins reset on
    # restart, which is the safe way to fail.
    SESSION_SECRET = secrets.token_urlsafe(48)
    print("[CONFIG] SESSION_SECRET is not set - using a temporary key, Steam logins will not survive a restart.")

# Behind a TLS-terminating proxy the session cookie must not travel over plain HTTP.
SESSION_HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "").strip().lower() in ("1", "true", "yes", "on")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=SESSION_HTTPS_ONLY,
)

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

OPEN_DOTA_API = "https://api.opendota.com/api"
STRATZ_GQL_API = os.getenv("STRATZ_GQL_API", "https://api.stratz.com/graphql").strip()
STRATZ_API_TOKEN = os.getenv("STRATZ_API_TOKEN", "").strip() or os.getenv("STRATZ_TOKEN", "").strip()
STEAM_API_KEY = os.getenv("STEAM_API_KEY", "").strip()
STEAM_OPENID_ENDPOINT = "https://steamcommunity.com/openid/login"
MAX_OFFSET_SEARCH = 2_000_000
RECENT_MATCHES_LIMIT = 120
# STRATZ rejects any request with take > 100 ("You have surpassed the maximum
# take value of : 100"), and one bad field fails the whole GraphQL response.
STRATZ_MAX_TAKE = 100
RECENT_TABLE_LIMIT = 10
RECENT_DETAIL_LIMIT = 6
ACTIVITY_DAYS = 365
MOST_PLAYED_LIMIT = 5
ALLIES_LIMIT = 6
TOP_HEROES_LIMIT = 5
STEAM64_BASE = 76561197960265728

hero_map = {}
item_map = {}
CACHE_TTL = 3600
player_cache = {}

RANK_MEDALS = {
    1: "Рекрут",
    2: "Страж",
    3: "Рыцарь",
    4: "Герой",
    5: "Легенда",
    6: "Властелин",
    7: "Божество",
    8: "Титан",
}

GAME_MODE_LABELS = {
    0: "Unknown",
    1: "All Pick",
    2: "Captains Mode",
    3: "Random Draft",
    4: "Single Draft",
    5: "All Random",
    11: "Mid Only",
    12: "Least Played",
    13: "New Player",
    15: "Custom",
    16: "Captains Draft",
    18: "Ability Draft",
    19: "Event",
    20: "All Random Deathmatch",
    22: "Ranked",
    23: "Turbo",
}

MONTH_LABELS_RU = ["янв.", "фев.", "мар.", "апр.", "май", "июн.", "июл.", "авг.", "сен.", "окт.", "ноя.", "дек."]
LANE_ROLE_LABELS = {
    1: "Safe Lane",
    2: "Mid Lane",
    3: "Off Lane",
    4: "Jungle",
    5: "Roam",
}


class CoachRequest(BaseModel):
    prompt: str
    snapshot: Dict[str, Any] = Field(default_factory=dict)
    selected_prompt_id: str = ""
    prompt_origin: str = ""
    conversation: List[Dict[str, Any]] = Field(default_factory=list)
    action_summary: Dict[str, Any] = Field(default_factory=dict)


def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_avg(values, digits=1):
    if not values:
        return 0
    return round(sum(values) / len(values), digits)


def is_match_win(match):
    if "is_victory" in match:
        return bool(match.get("is_victory"))
    if "isVictory" in match:
        return bool(match.get("isVictory"))
    if "is_win" in match:
        return bool(match.get("is_win"))

    player_slot = match.get("player_slot")
    radiant_win = match.get("radiant_win")

    if player_slot is None or radiant_win is None:
        return False

    return (player_slot < 128 and radiant_win) or (player_slot >= 128 and not radiant_win)


def parse_unix_timestamp(value):
    if value is None:
        return 0

    if isinstance(value, (int, float)):
        parsed = int(value)
        if parsed > 9_999_999_999:
            return parsed // 1000
        return parsed if parsed > 0 else 0

    text = str(value).strip()
    if not text:
        return 0

    if re.fullmatch(r"\d{10,13}", text):
        parsed = int(text)
        if parsed > 9_999_999_999:
            return parsed // 1000
        return parsed

    try:
        normalized = text.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(normalized)
        return int(dt.timestamp())
    except Exception:
        return 0


def format_match_date(timestamp):
    ts = to_int(timestamp, 0)
    if ts <= 0:
        return "Неизвестно"
    return datetime.datetime.fromtimestamp(ts, datetime.UTC).strftime("%d %b %Y")


def format_duration(duration_seconds):
    total = to_int(duration_seconds, 0)
    if total <= 0:
        return "--:--"

    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)

    if hours > 0:
        return f"{hours}:{minutes:02}:{seconds:02}"
    return f"{minutes}:{seconds:02}"


def format_time_ago(timestamp):
    ts = to_int(timestamp, 0)
    if ts <= 0:
        return "Неизвестно"

    now_ts = int(datetime.datetime.now(datetime.UTC).timestamp())
    delta = max(0, now_ts - ts)
    minutes = delta // 60
    hours = delta // 3600
    days = delta // 86_400

    if minutes < 1:
        return "только что"
    if minutes < 60:
        return f"{minutes} м назад"
    if hours < 24:
        return f"{hours} ч назад"
    if days < 30:
        return f"{days} д назад"
    if days < 365:
        return f"{days // 30} мес назад"
    return f"{days // 365} г назад"


def format_game_mode(game_mode):
    mode_id = to_int(game_mode, 0)
    return GAME_MODE_LABELS.get(mode_id, f"Mode {mode_id}")


def hero_image_url(hero_name):
    hero = hero_name or "unknown"
    return f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/{hero}.png"


def item_image_url(relative_path):
    if not relative_path:
        return ""
    if str(relative_path).startswith("http"):
        return relative_path
    return f"https://cdn.cloudflare.steamstatic.com{relative_path}"


def load_local_hero_map():
    if not os.path.exists(LOCAL_HEROES_PATH):
        return {}

    try:
        with open(LOCAL_HEROES_PATH, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except Exception:
        return {}

    if not isinstance(payload, dict):
        return {}

    parsed = {}
    for hero_id, hero_data in payload.items():
        if not isinstance(hero_data, dict):
            continue
        clean_id = to_int(hero_id, 0)
        if clean_id <= 0:
            continue
        short_name = str(hero_data.get("name") or "").replace("npc_dota_hero_", "").strip()
        if short_name:
            parsed[clean_id] = short_name
    return parsed


def load_local_item_map():
    if not os.path.exists(LOCAL_ITEMS_PATH):
        return {}

    try:
        with open(LOCAL_ITEMS_PATH, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except Exception:
        return {}

    if not isinstance(payload, dict):
        return {}

    parsed = {}
    for item_name, item_data in payload.items():
        if not isinstance(item_data, dict):
            continue
        item_id = to_int(item_data.get("id"), 0)
        if item_id <= 0:
            continue
        parsed[item_id] = {
            "name": item_data.get("dname") or str(item_name).replace("_", " ").title(),
            "image": item_image_url(item_data.get("img")),
            "slug": str(item_name or "").strip(),
        }
    return parsed


def average_positive(rows, field_name):
    if not isinstance(rows, list):
        return 0

    values = [to_int(row.get(field_name), 0) for row in rows if to_int(row.get(field_name), 0) > 0]
    if not values:
        return 0

    return int(round(sum(values) / len(values)))


def build_item_payload(item_id, is_neutral=False):
    clean_id = to_int(item_id, 0)
    if clean_id <= 0:
        return None

    item_data = item_map.get(clean_id, {})
    slug = str(item_data.get("slug") or "").strip()
    image = item_data.get("image") or (f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/{slug}.png" if slug else "")
    return {
        "id": clean_id,
        "name": item_data.get("name") or f"Item {clean_id}",
        "image": image,
        "slug": slug,
        "is_neutral": is_neutral,
    }


def steam64_to_account_id(steam_id64):
    steam_id64_int = to_int(steam_id64, 0)
    if steam_id64_int <= STEAM64_BASE:
        return None

    account_id = steam_id64_int - STEAM64_BASE
    return account_id if account_id > 0 else None


def extract_account_id_from_input(raw_query):
    query = str(raw_query or "").strip()
    if not query:
        return None

    # Common Dota profile URLs already contain account_id.
    players_match = re.search(r"/player[s]?/(\d+)", query, flags=re.IGNORECASE)
    if players_match:
        value = players_match.group(1)
        numeric = to_int(value, 0)
        if numeric >= STEAM64_BASE:
            return steam64_to_account_id(numeric)
        return numeric if numeric > 0 else None

    # Match URLs with account id in query string:
    # ...?steamAccountId=..., ...?account_id=..., ...?player_id=..., ...?id=...
    try:
        parsed = urllib.parse.urlparse(query)
        if parsed.scheme and parsed.netloc:
            query_params = urllib.parse.parse_qs(parsed.query)
            for key in ("steamAccountId", "steam_account_id", "account_id", "player_id", "id"):
                values = query_params.get(key)
                if not values:
                    continue
                numeric = to_int(values[0], 0)
                if numeric <= 0:
                    continue
                if numeric >= STEAM64_BASE:
                    return steam64_to_account_id(numeric)
                return numeric
    except Exception:
        pass

    # Steam profile URL with steam64 id.
    profile_match = re.search(r"steamcommunity\.com/profiles/(\d+)", query, flags=re.IGNORECASE)
    if profile_match:
        return steam64_to_account_id(profile_match.group(1))

    # Pure numeric input (account_id or steam64).
    if re.fullmatch(r"\d{5,20}", query):
        numeric = to_int(query, 0)
        if numeric >= STEAM64_BASE:
            return steam64_to_account_id(numeric)
        return numeric if numeric > 0 else None

    return None


def extract_steam_vanity_from_input(raw_query):
    query = str(raw_query or "").strip()
    if not query:
        return ""

    vanity_match = re.search(r"steamcommunity\.com/id/([^/?#]+)", query, flags=re.IGNORECASE)
    if vanity_match:
        return urllib.parse.unquote(vanity_match.group(1)).strip()

    return ""


def extract_account_id_from_steam_html(html_text):
    if not html_text:
        return None

    patterns = [
        r"<steamID64>\s*(\d{17,20})\s*</steamID64>",
        r"g_steamID\s*=\s*\"(\d{17,20})\"",
        r"\"steamid\"\s*:\s*\"(\d{17,20})\"",
    ]

    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE)
        if not match:
            continue
        account_id = steam64_to_account_id(match.group(1))
        if account_id:
            return account_id

    return None


async def resolve_steam_vanity_to_account_id(client, raw_query):
    vanity = extract_steam_vanity_from_input(raw_query)
    if not vanity:
        return None

    if STEAM_API_KEY:
        try:
            vanity_encoded = urllib.parse.quote_plus(vanity)
            api_url = (
                "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/"
                f"?key={urllib.parse.quote_plus(STEAM_API_KEY)}&vanityurl={vanity_encoded}"
            )
            response = await client.get(api_url)
            response.raise_for_status()
            payload = response.json()
            steam_id64 = (
                payload.get("response", {}).get("steamid")
                if isinstance(payload, dict)
                else None
            )
            account_id = steam64_to_account_id(steam_id64)
            if account_id:
                return account_id
        except (httpx.TimeoutException, httpx.RequestError):
            pass
        except Exception:
            pass

    # Fallback without Steam API key.
    # XML endpoint is usually easier to parse and more stable.
    try:
        profile_xml_url = f"https://steamcommunity.com/id/{urllib.parse.quote(vanity)}/?xml=1"
        response = await client.get(
            profile_xml_url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/xml,text/xml,text/html,*/*",
            },
        )
        response.raise_for_status()
        account_id = extract_account_id_from_steam_html(response.text)
        if account_id:
            return account_id
    except (httpx.TimeoutException, httpx.RequestError):
        pass
    except Exception:
        pass

    try:
        profile_url = f"https://steamcommunity.com/id/{urllib.parse.quote(vanity)}/"
        response = await client.get(
            profile_url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html,*/*",
            },
        )
        response.raise_for_status()
        account_id = extract_account_id_from_steam_html(response.text)
        if account_id:
            return account_id
    except (httpx.TimeoutException, httpx.RequestError):
        pass
    except Exception:
        pass

    return None


def build_search_terms(raw_query):
    query = str(raw_query or "").strip()
    if not query:
        return []

    terms = [query]

    # If user inserted steam vanity URL: steamcommunity.com/id/<name>
    vanity_match = re.search(r"steamcommunity\.com/id/([^/?#]+)", query, flags=re.IGNORECASE)
    if vanity_match:
        vanity = urllib.parse.unquote(vanity_match.group(1)).strip()
        if vanity:
            terms.append(vanity)

    # For arbitrary URLs fallback to trailing readable segment.
    try:
        parsed = urllib.parse.urlparse(query)
        if parsed.scheme and parsed.netloc:
            path_parts = [part for part in parsed.path.split("/") if part]
            if path_parts:
                tail = urllib.parse.unquote(path_parts[-1]).strip()
                if tail and not tail.isdigit():
                    terms.append(tail)
    except Exception:
        pass

    unique_terms = []
    for term in terms:
        clean_term = str(term).strip()
        if not clean_term:
            continue
        if clean_term not in unique_terms:
            unique_terms.append(clean_term)

    return unique_terms[:3]


def pick_search_result(results, original_query):
    if not isinstance(results, list) or not results:
        return None

    query_normalized = str(original_query or "").strip().lower()

    if query_normalized:
        for row in results:
            persona = str(row.get("personaname") or "").strip().lower()
            account_id = to_int(row.get("account_id"), 0)
            if persona == query_normalized and account_id > 0:
                return row

    for row in results:
        account_id = to_int(row.get("account_id"), 0)
        if account_id > 0:
            return row

    return None


def pick_player_from_match_detail(match_detail, account_id, fallback_match):
    players = match_detail.get("players")
    if not isinstance(players, list):
        return {}

    account_id_int = to_int(account_id, 0)
    if account_id_int > 0:
        for player in players:
            if to_int(player.get("account_id"), 0) == account_id_int:
                return player

    fallback_slot = to_int(fallback_match.get("player_slot"), -1)
    if fallback_slot >= 0:
        for player in players:
            if to_int(player.get("player_slot"), -2) == fallback_slot:
                return player

    fallback_hero = to_int(fallback_match.get("hero_id"), 0)
    if fallback_hero > 0:
        hero_candidates = [player for player in players if to_int(player.get("hero_id"), 0) == fallback_hero]
        if len(hero_candidates) == 1:
            return hero_candidates[0]

    return {}


def format_rank(rank_tier, leaderboard_rank):
    rank_tier = to_int(rank_tier, 0)
    if rank_tier <= 0:
        return "Без ранга"

    medal = rank_tier // 10
    star = rank_tier % 10
    medal_name = RANK_MEDALS.get(medal, "Без ранга")

    if medal == 8:
        if leaderboard_rank:
            return f"{medal_name} #{leaderboard_rank}"
        return medal_name

    if star > 0:
        return f"{medal_name} {star}"

    return medal_name


def get_cached_player_payload(player_id, stratz_only=False):
    cache_key = (to_int(player_id, 0), bool(stratz_only))
    entry = player_cache.get(cache_key)
    if not isinstance(entry, dict):
        return None

    cached_at = to_float(entry.get("cached_at"), 0)
    data = entry.get("data")
    age_seconds = datetime.datetime.now(datetime.UTC).timestamp() - cached_at
    if age_seconds < 0 or age_seconds > CACHE_TTL:
        player_cache.pop(cache_key, None)
        return None

    if not isinstance(data, dict) or data.get("error"):
        return None
    return data


def store_cached_player_payload(player_id, data, stratz_only=False):
    if not isinstance(data, dict) or data.get("error"):
        return

    cache_key = (to_int(player_id, 0), bool(stratz_only))
    player_cache[cache_key] = {
        "cached_at": datetime.datetime.now(datetime.UTC).timestamp(),
        "data": data,
    }


def json_payload_response(data):
    return Response(content=json.dumps(data, ensure_ascii=False), media_type="application/json")


def activity_label(matches_per_week):
    if matches_per_week >= 18:
        return "Очень высокая"
    if matches_per_week >= 10:
        return "Высокая"
    if matches_per_week >= 5:
        return "Средняя"
    if matches_per_week >= 2:
        return "Низкая"
    return "Очень низкая"


def build_activity_heatmap(matches, days=ACTIVITY_DAYS):
    today = datetime.datetime.now(datetime.UTC).date()
    start_day = today - datetime.timedelta(days=days - 1)

    day_counts = {start_day + datetime.timedelta(days=index): 0 for index in range(days)}

    for match in matches:
        timestamp = to_int(match.get("start_time"), 0)
        if timestamp <= 0:
            continue
            
        day = datetime.datetime.fromtimestamp(timestamp, datetime.UTC).date()
        if day in day_counts:
            day_counts[day] += 1

    max_count = max(day_counts.values()) if day_counts else 0
    total_matches = sum(day_counts.values())

    cells = []
    months = []
    seen_month_keys = set()
    seen_month_weeks = set()

    for offset in range(days):
        day = start_day + datetime.timedelta(days=offset)
        count = day_counts[day]
        week = offset // 7
        weekday = day.weekday()  

        intensity = 0
        if max_count > 0 and count > 0:
            intensity = min(4, max(1, int(round((count / max_count) * 4))))

        cells.append(
            {
                "date": day.isoformat(),
                "week": week,
                "weekday": weekday,
                "count": count,
                "intensity": intensity,
            }
        )

        # Подписываем только первые числа месяцев и не больше одной подписи на
        # колонку. Раньше сюда попадал ещё и день offset == 0: неполный первый
        # месяц и первое число следующего оказывались в одной неделе, обе подписи
        # получали одну grid-колонку и наезжали друг на друга.
        if day.day == 1 and week not in seen_month_weeks:
            month_key = (day.year, day.month)
            if month_key not in seen_month_keys:
                seen_month_keys.add(month_key)
                seen_month_weeks.add(week)
                months.append(
                    {
                        "week": week,
                        "label": MONTH_LABELS_RU[day.month - 1],
                    }
                )

    weeks = (days + 6) // 7
    matches_per_week = (total_matches / days) * 7 if days > 0 else 0

    return {
        "weeks": weeks,
        "cells": cells,
        "months": months,
        "total_matches": total_matches,
        "max_day_matches": max_count,
        "label": activity_label(matches_per_week),
        "status_tone": "high" if matches_per_week >= 10 else "medium" if matches_per_week >= 5 else "low",
        "matches_per_week": round(matches_per_week, 1),
        "window_days": days,
    }


def build_most_played_heroes(hero_rows, total_matches):
    if not isinstance(hero_rows, list):
        return []

    heroes = []
    for row in hero_rows:
        hero_id = row.get("hero_id")
        games = to_int(row.get("games"), 0)
        wins = to_int(row.get("win"), 0)

        if hero_id is None or games <= 0:
            continue

        winrate = round((wins / games) * 100, 1) if games > 0 else 0
        pick_rate = round((games / total_matches) * 100, 1) if total_matches > 0 else 0

        heroes.append(
            {
                "hero_name": hero_map.get(hero_id, "unknown"),
                "games": games,
                "wins": wins,
                "winrate": winrate,
                "pick_rate": pick_rate,
            }
        )

    heroes.sort(key=lambda item: item["games"], reverse=True)
    return heroes[:MOST_PLAYED_LIMIT]


def build_top_allies(peers_rows):
    if not isinstance(peers_rows, list):
        return []

    allies = []
    for peer in peers_rows:
        games = to_int(peer.get("with_games"), to_int(peer.get("games"), 0))
        wins = to_int(peer.get("with_win"), to_int(peer.get("win"), 0))

        if games <= 0:
            continue

        winrate = round((wins / games) * 100, 1) if games > 0 else 0
        name = peer.get("personaname") or f"Player {peer.get('account_id', '?')}"

        allies.append(
            {
                "name": name,
                "avatar": peer.get("avatarfull") or peer.get("avatar") or "",
                "games": games,
                "wins": wins,
                "winrate": winrate,
            }
        )

    allies.sort(key=lambda item: item["games"], reverse=True)
    return allies[:ALLIES_LIMIT]


def build_meta_guides(top_heroes, most_played_heroes=None, limit=5):
    """Руководства по героям, на которых игрок реально играет.

    Раньше здесь был статический каталог из двенадцати придуманных гайдов с
    выдуманными лайками. Если ни один герой игрока в него не попадал - обычный
    случай - панель показывала чужих героев. Теперь герои берутся из пула самого
    игрока, а содержание руководства определяется его ролью.
    """
    rows = []
    seen = set()

    # Сначала вся история, затем текущее окно: "чаще всего играет" - это про
    # накопленную статистику, окно лишь дополняет её свежими героями.
    for source in (most_played_heroes, top_heroes):
        if not isinstance(source, list):
            continue

        for hero in source:
            if not isinstance(hero, dict):
                continue

            hero_name = str(hero.get("hero_name") or "").strip()
            games = to_int(hero.get("games"), 0)
            if not hero_name or hero_name == "unknown" or hero_name in seen or games <= 0:
                continue

            seen.add(hero_name)
            role = HERO_ROLE_HINTS.get(hero_name, "")
            guide = HERO_GUIDE_BY_ROLE.get(role, HERO_GUIDE_DEFAULT)
            rows.append(
                {
                    "hero_name": hero_name,
                    "hero_image": hero_image_url(hero_name),
                    "role": role or "Универсал",
                    "plan": guide["plan"],
                    "early": guide["early"],
                    "items": guide["items"],
                    "mistake": guide["mistake"],
                    # Не для показа: только чтобы отсортировать пул по частоте.
                    "_games": games,
                }
            )

    rows.sort(key=lambda item: item["_games"], reverse=True)
    for row in rows:
        row.pop("_games", None)
    return rows[:limit]


def totals_average(totals_rows, field_name):
    if not isinstance(totals_rows, list):
        return 0

    for row in totals_rows:
        if row.get("field") != field_name:
            continue

        n = to_int(row.get("n"), 0)
        total_sum = to_float(row.get("sum"), 0.0)
        if n > 0:
            return int(round(total_sum / n))

    return 0


def build_top_heroes_from_matches(matches, limit=TOP_HEROES_LIMIT):
    hero_stats = defaultdict(lambda: {"games": 0, "wins": 0, "kills": 0, "deaths": 0, "assists": 0, "gpm": 0, "gpm_games": 0})

    for match in matches:
        hero_id = match.get("hero_id")
        if hero_id is None:
            continue

        stat = hero_stats[hero_id]
        stat["games"] += 1
        if is_match_win(match):
            stat["wins"] += 1
        stat["kills"] += to_int(match.get("kills"), 0)
        stat["deaths"] += to_int(match.get("deaths"), 0)
        stat["assists"] += to_int(match.get("assists"), 0)
        gpm = to_int(match.get("gold_per_min"), 0)
        if gpm > 0:
            stat["gpm"] += gpm
            stat["gpm_games"] += 1

    top_heroes = []
    for hero_id, stat in hero_stats.items():
        games = stat["games"]
        wins = stat["wins"]
        if games <= 0:
            continue

        avg_deaths = stat["deaths"] / games
        top_heroes.append(
            {
                "hero_name": hero_map.get(hero_id, "unknown"),
                "games": games,
                "wins": wins,
                "losses": games - wins,
                "winrate": round((wins / games) * 100, 1),
                # Разбивка нужна панели трендов: по клику на герое в кольце
                # показываются его реальные показатели, а не только винрейт.
                "avg_kills": round(stat["kills"] / games, 1),
                "avg_deaths": round(avg_deaths, 1),
                "avg_assists": round(stat["assists"] / games, 1),
                "avg_kda": round((stat["kills"] + stat["assists"]) / (avg_deaths if avg_deaths > 0 else 1), 2),
                "avg_gpm": int(round(stat["gpm"] / stat["gpm_games"])) if stat["gpm_games"] > 0 else 0,
            }
        )

    top_heroes.sort(key=lambda item: item["games"], reverse=True)
    return top_heroes[:limit]


def compute_window_stats(matches_subset):
    total = len(matches_subset)
    wins = sum(1 for match in matches_subset if is_match_win(match))
    losses = total - wins

    recent_wr = round((wins / total) * 100, 1) if total > 0 else 0

    kills_values = [to_int(match.get("kills"), 0) for match in matches_subset]
    deaths_values = [to_int(match.get("deaths"), 0) for match in matches_subset]
    assists_values = [to_int(match.get("assists"), 0) for match in matches_subset]
    gpm_values = [to_int(match.get("gold_per_min"), 0) for match in matches_subset if to_int(match.get("gold_per_min"), 0) > 0]
    xpm_values = [to_int(match.get("xp_per_min"), 0) for match in matches_subset if to_int(match.get("xp_per_min"), 0) > 0]

    avg_kills = safe_avg(kills_values, 1)
    avg_deaths = safe_avg(deaths_values, 1)
    avg_assists = safe_avg(assists_values, 1)
    avg_kda = round((avg_kills + avg_assists) / (avg_deaths if avg_deaths > 0 else 1), 2)
    avg_gpm = int(round(safe_avg(gpm_values, 2), 0)) if gpm_values else 0
    avg_xpm = int(round(safe_avg(xpm_values, 2), 0)) if xpm_values else 0

    top_heroes = build_top_heroes_from_matches(matches_subset, TOP_HEROES_LIMIT)
    # Кольцо отдаётся объектами, а не именами: панель трендов показывает по клику
    # показатели героя, и тянуть их вторым запросом было бы незачем.
    hero_ring = build_top_heroes_from_matches(matches_subset, 12)
    unique_heroes = len({match.get("hero_id") for match in matches_subset if match.get("hero_id") is not None})

    trend_points = []
    for match in matches_subset[::-1]:
        hero_id = match.get("hero_id")
        hero_name = hero_map.get(hero_id, "unknown")
        trend_points.append(
            {
                "result": 1 if is_match_win(match) else -1,
                "hero_name": hero_name,
            }
        )

    lane_known = [match for match in matches_subset if match.get("lane_role") is not None]
    lane_wins = sum(1 for match in lane_known if is_match_win(match))
    lane_losses = len(lane_known) - lane_wins
    lane_unknown = total - len(lane_known)

    lane_stats = defaultdict(lambda: {"games": 0, "wins": 0})
    for match in matches_subset:
        lane_role = to_int(match.get("lane_role"), 0)
        if lane_role <= 0:
            continue

        lane_stats[lane_role]["games"] += 1
        if is_match_win(match):
            lane_stats[lane_role]["wins"] += 1

    lane_breakdown = []
    for lane_role, stats in lane_stats.items():
        lane_games = stats["games"]
        lane_wins_count = stats["wins"]
        lane_breakdown.append(
            {
                "lane_role": lane_role,
                "label": LANE_ROLE_LABELS.get(lane_role, f"Lane {lane_role}"),
                "games": lane_games,
                "wins": lane_wins_count,
                "winrate": round((lane_wins_count / lane_games) * 100, 1) if lane_games > 0 else 0,
            }
        )

    lane_breakdown.sort(key=lambda item: item["games"], reverse=True)
    best_lane = lane_breakdown[0] if lane_breakdown else None

    party_known = [to_int(match.get("party_size"), 1) for match in matches_subset if match.get("party_size") is not None]
    if party_known:
        party_games = sum(1 for size in party_known if size > 1)
        solo_games = len(party_known) - party_games
        party_rate = round((party_games / len(party_known)) * 100, 1)
        solo_rate = round((solo_games / len(party_known)) * 100, 1)
    else:
        party_rate = 0
        solo_rate = 0

    return {
        "matches": total,
        "wins": wins,
        "losses": losses,
        "recent_wr": recent_wr,
        "avg_kda": avg_kda,
        "avg_kills": avg_kills,
        "avg_deaths": avg_deaths,
        "avg_assists": avg_assists,
        "avg_gpm": avg_gpm,
        "avg_xpm": avg_xpm,
        "win_trend": [point["result"] for point in trend_points],
        "trend_points": trend_points,
        "top_heroes": top_heroes,
        "hero_ring": hero_ring,
        "lane_record": {
            "wins": lane_wins,
            "losses": lane_losses,
            "unknown": lane_unknown,
        },
        "lane_breakdown": lane_breakdown,
        "best_lane": best_lane,
        "party_rate": party_rate,
        "solo_rate": solo_rate,
        "unique_heroes": unique_heroes,
        "radar_data": {
            "farming": min(100, int(avg_gpm / 8)) if avg_gpm > 0 else 0,
            "fighting": min(100, int((avg_kills + avg_assists) * 2)) if total > 0 else 0,
            "survivability": min(100, int(avg_kda * 15)) if total > 0 else 0,
            "experience": min(100, int(avg_xpm / 9)) if avg_xpm > 0 else 0,
            "versatility": min(100, unique_heroes * 5),
        },
    }


def compute_winrate_delta(matches, window_size):
    current = matches[:window_size]
    previous = matches[window_size : window_size * 2]

    if len(current) == 0 or len(previous) == 0:
        return 0

    current_wins = sum(1 for match in current if is_match_win(match))
    previous_wins = sum(1 for match in previous if is_match_win(match))

    current_wr = (current_wins / len(current)) * 100
    previous_wr = (previous_wins / len(previous)) * 100
    return round(current_wr - previous_wr, 1)


STRATZ_GAME_MODE_IDS = {
    "NONE": 0,
    "ALL_PICK": 1,
    "CAPTAINS_MODE": 2,
    "RANDOM_DRAFT": 3,
    "SINGLE_DRAFT": 4,
    "ALL_RANDOM": 5,
    "INTRO": 6,
    "THE_DIRETIDE": 7,
    "REVERSE_CAPTAINS_MODE": 8,
    "THE_GREEVILING": 9,
    "TUTORIAL": 10,
    "MID_ONLY": 11,
    "LEAST_PLAYED": 12,
    "NEW_PLAYER_POOL": 13,
    "COMPENDIUM_MATCHMAKING": 14,
    "CUSTOM": 15,
    "CAPTAINS_DRAFT": 16,
    "BALANCED_DRAFT": 17,
    "ABILITY_DRAFT": 18,
    "EVENT": 19,
    "ALL_RANDOM_DEATH_MATCH": 20,
    "SOLO_MID": 21,
    "ALL_PICK_RANKED": 22,
    "TURBO": 23,
    "MUTATION": 24,
    "UNKNOWN": 0,
}


def map_stratz_game_mode(value):
    # STRATZ answers with the enum name ("TURBO"), not the numeric id the rest of
    # the app uses, so a plain to_int() labelled every match "Unknown" and hid
    # turbo games from the turbo counters.
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value or "").strip().upper()
    if not text:
        return 0
    if text.isdigit():
        return to_int(text, 0)
    return STRATZ_GAME_MODE_IDS.get(text, 0)


def map_stratz_position_to_lane_role(position):
    if position is None:
        return None

    if isinstance(position, (int, float)):
        clean = int(position)
        return clean if 1 <= clean <= 5 else None

    text = str(position).strip().upper()
    if not text:
        return None

    aliases = {
        "POSITION_1": 1,
        "POSITION1": 1,
        "SAFE_LANE": 1,
        "SAFELANE": 1,
        "CARRY": 1,
        "POSITION_2": 2,
        "POSITION2": 2,
        "MIDDLE_LANE": 2,
        "MID_LANE": 2,
        "MID": 2,
        "POSITION_3": 3,
        "POSITION3": 3,
        "OFF_LANE": 3,
        "OFFLANE": 3,
        "POSITION_4": 5,
        "POSITION4": 5,
        "SOFT_SUPPORT": 5,
        "ROAM": 5,
        "POSITION_5": 5,
        "POSITION5": 5,
        "HARD_SUPPORT": 5,
        "SUPPORT": 5,
    }
    if text in aliases:
        return aliases[text]

    number_match = re.search(r"(\d)", text)
    if number_match:
        guessed = to_int(number_match.group(1), 0)
        return guessed if 1 <= guessed <= 5 else None

    return None


def is_stratz_configured():
    return bool(STRATZ_GQL_API and STRATZ_API_TOKEN)


def build_stratz_headers():
    # STRATZ routes API-token traffic by User-Agent: a browser-looking UA gets
    # bounced by Cloudflare with 403. Do not add Origin/Referer/Sec-Fetch-* or a
    # manual Accept-Encoding either - they trigger the same block, and a
    # hand-rolled "br" leaves httpx with a body it cannot decode.
    return {
        "Authorization": f"Bearer {STRATZ_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "STRATZ_API",
    }


def first_list_object(value):
    if isinstance(value, list):
        for row in value:
            if isinstance(row, dict):
                return row
    return {}


def normalize_stratz_match_row(match_node, player_node):
    duration = to_int(match_node.get("durationSeconds"), 0)
    start_time = parse_unix_timestamp(match_node.get("startDateTime"))
    if start_time <= 0:
        end_time = parse_unix_timestamp(match_node.get("endDateTime"))
        if end_time > 0 and duration > 0:
            start_time = max(0, end_time - duration)
        elif end_time > 0:
            start_time = end_time

    hero_id = to_int(player_node.get("heroId"), 0)
    hero_obj = player_node.get("hero")
    if hero_id <= 0 and isinstance(hero_obj, dict):
        hero_id = to_int(hero_obj.get("id"), 0)

    lane_role = map_stratz_position_to_lane_role(player_node.get("position"))

    return {
        "match_id": to_int(match_node.get("id"), 0),
        "start_time": start_time,
        "duration": duration,
        "game_mode": map_stratz_game_mode(match_node.get("gameMode")),
        "lobby_type": to_int(match_node.get("lobbyType"), 0),
        "hero_id": hero_id,
        "kills": to_int(player_node.get("kills"), 0),
        "deaths": to_int(player_node.get("deaths"), 0),
        "assists": to_int(player_node.get("assists"), 0),
        "level": to_int(player_node.get("level"), 0),
        "gold_per_min": to_int(player_node.get("goldPerMinute"), 0),
        "xp_per_min": to_int(player_node.get("experiencePerMinute"), 0),
        "lane_role": lane_role,
        # STRATZ не отдаёт размер группы, но partyId заполнен только когда игрок
        # играл в пати. Раньше здесь всегда стоял None, и панель соло/группа
        # показывала 0% на любом профиле.
        "party_size": 2 if player_node.get("partyId") is not None else 1,
        "is_victory": bool(player_node.get("isVictory")),
        "is_win": bool(player_node.get("isVictory")),
        "item_0": to_int(player_node.get("item0Id"), 0),
        "item_1": to_int(player_node.get("item1Id"), 0),
        "item_2": to_int(player_node.get("item2Id"), 0),
        "item_3": to_int(player_node.get("item3Id"), 0),
        "item_4": to_int(player_node.get("item4Id"), 0),
        "item_5": to_int(player_node.get("item5Id"), 0),
        "item_neutral": to_int(player_node.get("neutral0Id"), 0),
    }


async def fetch_stratz_graphql(client, query, variables=None):
    if not is_stratz_configured():
        return None

    payload = {"query": query}
    if isinstance(variables, dict):
        payload["variables"] = variables

    try:
        response = await client.post(
            STRATZ_GQL_API,
            headers=build_stratz_headers(),
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            return None

        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            return None

        data = body.get("data")
        return data if isinstance(data, dict) else None
    except Exception:
        return None


async def ensure_stratz_constants(client):
    global hero_map, item_map

    if not hero_map:
        heroes_query = """
        query StratzHeroes {
          constants {
            heroes {
              id
              shortName
              name
            }
          }
        }
        """
        heroes_data = await fetch_stratz_graphql(client, heroes_query)
        heroes_root = heroes_data.get("constants", {}) if isinstance(heroes_data, dict) else {}
        heroes_rows = heroes_root.get("heroes") if isinstance(heroes_root.get("heroes"), list) else []
        parsed_heroes = {}
        for hero in heroes_rows:
            if not isinstance(hero, dict):
                continue
            hero_id = to_int(hero.get("id"), 0)
            if hero_id <= 0:
                continue
            short_name = str(hero.get("shortName") or hero.get("name") or "").replace("npc_dota_hero_", "").strip()
            if short_name:
                parsed_heroes[hero_id] = short_name
        if parsed_heroes:
            hero_map = parsed_heroes

    if not hero_map:
        hero_map = load_local_hero_map()

    if not item_map:
        item_queries = [
            """
            query StratzItems {
              constants {
                items {
                  id
                  shortName
                  displayName
                }
              }
            }
            """,
            """
            query StratzItemsFallback {
              constants {
                items {
                  id
                  shortName
                  name
                }
              }
            }
            """,
        ]

        parsed_items = {}
        for item_query in item_queries:
            items_data = await fetch_stratz_graphql(client, item_query)
            items_root = items_data.get("constants", {}) if isinstance(items_data, dict) else {}
            items_rows = items_root.get("items") if isinstance(items_root.get("items"), list) else []

            for item in items_rows:
                if not isinstance(item, dict):
                    continue
                item_id = to_int(item.get("id"), 0)
                if item_id <= 0:
                    continue

                short_name = str(item.get("shortName") or "").strip()
                if not short_name:
                    continue

                display_name = item.get("displayName") or item.get("name") or short_name.replace("_", " ").title()
                parsed_items[item_id] = {
                    "name": display_name,
                    "image": f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/{short_name}.png",
                    "slug": short_name,
                }

            if parsed_items:
                break

        # STRATZ's item constants are incomplete: several neutral items (Hydra's
        # Breath, Conjurer's Catalyst, ...) are missing from them outright. Keeping
        # only the first source that answered left those slots rendering as
        # "Item 1858" with no icon, so fill the gaps from the bundled copy - it is
        # on disk, so this costs no extra request.
        for local_item_id, local_payload in load_local_item_map().items():
            parsed_items.setdefault(local_item_id, local_payload)

        item_map = parsed_items

    if not item_map:
        # Neither STRATZ nor the bundled file produced anything usable.
        items_response = await fetch_json(client, f"{OPEN_DOTA_API}/constants/items", {}, label="items_fallback", max_retries=1)
        if isinstance(items_response, dict):
            parsed_items = {}
            for item_name, item_data in items_response.items():
                if not isinstance(item_data, dict):
                    continue
                item_id = to_int(item_data.get("id"), 0)
                if item_id <= 0:
                    continue
                parsed_items[item_id] = {
                    "name": item_data.get("dname") or str(item_name).replace("_", " ").title(),
                    "image": item_image_url(item_data.get("img")),
                    "slug": str(item_name or "").strip(),
                }
            if parsed_items:
                item_map = parsed_items


async def fetch_stratz_player_payload(client, player_id):
    variables = {
        "playerId": int(player_id),
        "take": min(RECENT_MATCHES_LIMIT, STRATZ_MAX_TAKE),
    }

    rich_query = """
    query StratzPlayerCore($playerId: Long!, $take: Int!) {
      player(steamAccountId: $playerId) {
        steamAccountId
        firstMatchDate
        matchCount
        winCount
        steamAccount {
          name
          avatar
          seasonRank
          seasonLeaderboardRank
        }
        # No isParsed filter: it keeps only replay-parsed games, which quietly drops
        # most turbo matches from the sample and skews every window stat with it.
        # Lane role (position) is missing on unparsed games, and that degrades
        # gracefully - a skewed match list does not.
        recentMatches: matches(request: { take: $take, playerList: SINGLE }) {
          id
          startDateTime
          endDateTime
          durationSeconds
          gameMode
          lobbyType
          players(steamAccountId: $playerId) {
            isVictory
            position
            partyId
            kills
            deaths
            assists
            level
            heroId
            goldPerMinute
            experiencePerMinute
            item0Id
            item1Id
            item2Id
            item3Id
            item4Id
            item5Id
            neutral0Id
          }
        }
      }
    }
    """
    rich_data = await fetch_stratz_graphql(client, rich_query, variables)
    player = rich_data.get("player") if isinstance(rich_data, dict) else None
    if isinstance(player, dict):
        return player

    fallback_query = """
    query StratzPlayerCoreFallback($playerId: Long!, $take: Int!) {
      player(steamAccountId: $playerId) {
        steamAccountId
        firstMatchDate
        matchCount
        winCount
        steamAccount {
          name
          avatar
          seasonRank
          seasonLeaderboardRank
        }
        recentMatches: matches(request: { take: $take, playerList: SINGLE }) {
          id
          startDateTime
          durationSeconds
          players(steamAccountId: $playerId) {
            isVictory
            partyId
            kills
            deaths
            assists
            level
            heroId
            goldPerMinute
            experiencePerMinute
            item0Id
            item1Id
            item2Id
            item3Id
            item4Id
            item5Id
            neutral0Id
          }
        }
      }
    }
    """
    fallback_data = await fetch_stratz_graphql(client, fallback_query, variables)
    player = fallback_data.get("player") if isinstance(fallback_data, dict) else None
    return player if isinstance(player, dict) else None


async def fetch_stratz_match_detail(client, player_id, match_id):
    query = """
    query StratzMatchDetails($playerId: Long!, $matchId: Long!) {
      match(id: $matchId) {
        id
        startDateTime
        durationSeconds
        gameMode
        lobbyType
        players(steamAccountId: $playerId) {
          isVictory
          position
          kills
          deaths
          assists
          level
          heroId
          goldPerMinute
          experiencePerMinute
          item0Id
          item1Id
          item2Id
          item3Id
          item4Id
          item5Id
          neutral0Id
          hero {
            shortName
          }
        }
      }
    }
    """
    variables = {"playerId": int(player_id), "matchId": int(match_id)}
    payload = await fetch_stratz_graphql(client, query, variables)
    return payload.get("match") if isinstance(payload, dict) else None


async def get_player_data_from_stratz(client, player_id):
    if not is_stratz_configured():
        return None

    print(f"[STRATZ] Fetching data for player {player_id}")
    await ensure_stratz_constants(client)
    player_payload = await fetch_stratz_player_payload(client, player_id)
    if not isinstance(player_payload, dict):
        print(f"[STRATZ] Failed to get player payload")
        return None

    steam = player_payload.get("steamAccount")
    if not isinstance(steam, dict):
        print(f"[STRATZ] No steam account found")
        return None

    recent_matches_nodes = player_payload.get("recentMatches") if isinstance(player_payload.get("recentMatches"), list) else []
    print(f"[STRATZ] Got {len(recent_matches_nodes)} recent matches")
    matches_raw = []
    for match_node in recent_matches_nodes:
        if not isinstance(match_node, dict):
            continue
        players = match_node.get("players")
        if not isinstance(players, list) or not players:
            continue
        player_row = players[0] if isinstance(players[0], dict) else {}
        normalized = normalize_stratz_match_row(match_node, player_row)
        if normalized.get("match_id", 0) > 0:
            matches_raw.append(normalized)

    print(f"[STRATZ] Normalized {len(matches_raw)} matches")
    matches_raw.sort(key=lambda row: to_int(row.get("start_time"), 0), reverse=True)
    if not matches_raw:
        print(f"[STRATZ] No valid matches")
        return None

    window_25_matches = matches_raw[:25]
    window_100_matches = matches_raw[:100]

    window_stats_25 = compute_window_stats(window_25_matches)
    window_stats_100 = compute_window_stats(window_100_matches)
    window_stats_25["winrate_delta"] = compute_winrate_delta(matches_raw, 25)
    window_stats_100["winrate_delta"] = compute_winrate_delta(matches_raw, 100)

    windows = {
        "25": window_stats_25,
        "100": window_stats_100,
    }
    default_window = window_stats_25 if window_stats_25["matches"] > 0 else window_stats_100

    # "take" in matchesGroupBy caps how many matches are folded into each group,
    # not how many groups come back, so asking for take: 1 reported a career total
    # of exactly 1 match. Lifetime totals live on the player node itself.
    total_matches = to_int(player_payload.get("matchCount"), 0)
    wins_all = to_int(player_payload.get("winCount"), 0)
    if total_matches <= 0:
        total_matches = default_window["matches"]
        wins_all = default_window["wins"]

    losses_all = max(0, total_matches - wins_all)
    total_wr = round((wins_all / total_matches) * 100, 2) if total_matches > 0 else 0

    # No lifetime turbo aggregate is available for the same reason; approximate it
    # from the recent-match sample.
    turbo_sample = [match for match in matches_raw if to_int(match.get("game_mode"), 0) == 23]
    turbo_total = len(turbo_sample)
    turbo_wins = sum(1 for match in turbo_sample if is_match_win(match))
    turbo_losses = max(0, turbo_total - turbo_wins)
    turbo_wr = round((turbo_wins / turbo_total) * 100, 2) if turbo_total > 0 else 0

    # Статистика по героям за всю историю берётся у OpenDota. У STRATZ такого
    # агрегата нет: и matchesGroupBy, и heroesPerformance трактуют take как число
    # учитываемых МАТЧЕЙ, а не групп, поэтому "самые играемые" считались по
    # последним ста играм, а пикрейт делился на счётчик за всю карьеру и всегда
    # выходил 0.0-0.1%.
    heroes_totals_raw = await fetch_json(
        client,
        f"{OPEN_DOTA_API}/players/{player_id}/heroes?significant=0",
        [],
        label="heroes_totals_stratz",
        max_retries=1,
    )
    if not isinstance(heroes_totals_raw, list):
        heroes_totals_raw = []

    gpm_fallback = average_positive(matches_raw, "gold_per_min")
    xpm_fallback = average_positive(matches_raw, "xp_per_min")
    for window_key in ("25", "100"):
        if windows[window_key]["avg_gpm"] <= 0 and gpm_fallback > 0:
            windows[window_key]["avg_gpm"] = gpm_fallback
        if windows[window_key]["avg_xpm"] <= 0 and xpm_fallback > 0:
            windows[window_key]["avg_xpm"] = xpm_fallback

    recent_matches_source = matches_raw[:RECENT_TABLE_LIMIT]
    match_details = {}
    detail_tasks = []
    detail_ids = []
    for match in recent_matches_source:
        match_id = to_int(match.get("match_id"), 0)
        if match_id <= 0:
            continue
        detail_ids.append(match_id)
        detail_tasks.append(fetch_stratz_match_detail(client, player_id, match_id))

    if detail_tasks:
        detail_results = await asyncio.gather(*detail_tasks)
        for match_id, detail in zip(detail_ids, detail_results):
            if isinstance(detail, dict):
                match_details[match_id] = detail

    recent_matches_prepared = []
    for match in recent_matches_source:
        match_id = to_int(match.get("match_id"), 0)
        detail = match_details.get(match_id, {})
        detail_player = first_list_object(detail.get("players") if isinstance(detail, dict) else [])

        detail_hero = detail_player.get("hero")
        detail_hero_short = ""
        if isinstance(detail_hero, dict):
            detail_hero_short = str(detail_hero.get("shortName") or "").strip()

        hero_id = to_int(detail_player.get("heroId"), to_int(match.get("hero_id"), 0))
        hero_name = detail_hero_short or hero_map.get(hero_id, "unknown")
        start_time = parse_unix_timestamp(detail.get("startDateTime")) if isinstance(detail, dict) else 0
        if start_time <= 0:
            start_time = to_int(match.get("start_time"), 0)

        duration_seconds = to_int(detail.get("durationSeconds"), to_int(match.get("duration"), 0)) if isinstance(detail, dict) else to_int(match.get("duration"), 0)
        mode_id = map_stratz_game_mode(detail.get("gameMode")) if isinstance(detail, dict) else 0
        if mode_id <= 0:
            mode_id = to_int(match.get("game_mode"), 0)
        is_win = bool(detail_player.get("isVictory")) if detail_player else is_match_win(match)

        items = []
        for item_slot in range(6):
            item_id = detail_player.get(f"item{item_slot}Id")
            if to_int(item_id, 0) <= 0:
                item_id = match.get(f"item_{item_slot}")
            item_payload = build_item_payload(item_id)
            if item_payload:
                items.append(item_payload)
        neutral_item_id = detail_player.get("neutral0Id")
        if to_int(neutral_item_id, 0) <= 0:
            neutral_item_id = match.get("item_neutral")
        neutral_item = build_item_payload(neutral_item_id, is_neutral=True)
        if neutral_item:
            items.append(neutral_item)

        recent_matches_prepared.append(
            {
                "match_id": match_id,
                "player_slot": 0,
                "radiant_win": is_win,
                "is_win": is_win,
                "hero_id": hero_id,
                "hero_name": hero_name,
                "hero_image": hero_image_url(hero_name),
                "kills": to_int(detail_player.get("kills"), to_int(match.get("kills"), 0)),
                "deaths": to_int(detail_player.get("deaths"), to_int(match.get("deaths"), 0)),
                "assists": to_int(detail_player.get("assists"), to_int(match.get("assists"), 0)),
                "kda_impact": to_int(detail_player.get("kills"), to_int(match.get("kills"), 0))
                + to_int(detail_player.get("assists"), to_int(match.get("assists"), 0))
                - to_int(detail_player.get("deaths"), to_int(match.get("deaths"), 0)),
                "level": to_int(detail_player.get("level"), to_int(match.get("level"), 0)),
                "game_mode": mode_id,
                "game_mode_label": format_game_mode(mode_id),
                "duration": duration_seconds,
                "duration_label": format_duration(duration_seconds),
                "match_date": format_match_date(start_time),
                "time_ago": format_time_ago(start_time),
                "start_time": start_time,
                "items": items,
            }
        )

    rank_tier = to_int(steam.get("seasonRank"), 0)
    leaderboard_rank = to_int(steam.get("seasonLeaderboardRank"), 0)
    if leaderboard_rank <= 0:
        leaderboard_rank = None

    most_played_heroes = build_most_played_heroes(heroes_totals_raw, total_matches)
    if not most_played_heroes:
        most_played_heroes = [
            {
                "hero_name": hero["hero_name"],
                "games": hero["games"],
                "wins": round(hero["games"] * (hero["winrate"] / 100)),
                "winrate": round(hero["winrate"], 1),
                "pick_rate": round((hero["games"] / default_window["matches"]) * 100, 1) if default_window["matches"] > 0 else 0,
            }
            for hero in sorted(default_window["top_heroes"], key=lambda item: item["games"], reverse=True)[:MOST_PLAYED_LIMIT]
        ]

    first_match_ts = parse_unix_timestamp(player_payload.get("firstMatchDate"))
    first_match_date = format_match_date(first_match_ts) if first_match_ts > 0 else format_match_date(matches_raw[-1].get("start_time"))

    # STRATZ has no cheap "top allies" aggregate, so peers still come from OpenDota
    # the same way the activity heatmap already does.
    activity_matches, peers_raw = await asyncio.gather(
        fetch_year_activity_matches(client, player_id, days=ACTIVITY_DAYS),
        # One retry: without it a single transient DNS/network blip silently leaves
        # the allies panel empty, with no way for the UI to tell that apart from
        # "this player has no recorded team-mates".
        fetch_json(client, f"{OPEN_DOTA_API}/players/{player_id}/peers", [], label="peers_stratz", max_retries=1),
    )
    activity = build_activity_heatmap(activity_matches if activity_matches else matches_raw, ACTIVITY_DAYS)
    meta_guides = build_meta_guides(default_window["top_heroes"], most_played_heroes, limit=5)

    return {
        # Стабильный ключ профиля: ник и ранг меняются, поэтому привязывать к ним
        # что-либо на фронтенде нельзя.
        "account_id": to_int(player_id, 0),
        "name": steam.get("name", "Unknown"),
        "avatar": steam.get("avatar", ""),
        "rank": format_rank(rank_tier, leaderboard_rank),
        "rank_tier": rank_tier,
        "leaderboard_rank": leaderboard_rank,
        "total_matches": total_matches,
        "total_wr": total_wr,
        "wins": wins_all,
        "losses": losses_all,
        "first_match": first_match_date,
        "recent_wr": default_window["recent_wr"],
        "win_trend": default_window["win_trend"],
        "avg_kda": default_window["avg_kda"],
        "avg_kills": default_window["avg_kills"],
        "avg_deaths": default_window["avg_deaths"],
        "avg_assists": default_window["avg_assists"],
        "avg_gpm": windows["25"]["avg_gpm"] if windows["25"]["matches"] > 0 else windows["100"]["avg_gpm"],
        "avg_xpm": windows["25"]["avg_xpm"] if windows["25"]["matches"] > 0 else windows["100"]["avg_xpm"],
        "turbo_stats": {
            "matches": turbo_total,
            "wins": turbo_wins,
            "losses": turbo_losses,
            "wr": turbo_wr,
        },
        "top_heroes": default_window["top_heroes"],
        "most_played_heroes": most_played_heroes,
        "top_allies": build_top_allies(peers_raw),
        "meta_guides": meta_guides,
        "activity": activity,
        "matches": recent_matches_prepared,
        "windows": windows,
        "radar_data": default_window["radar_data"],
    }


async def fetch_json(client, url, default_value, label="request", max_retries=2, request_timeout=None):
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                print(f"[PLAYER] {label}: Retry attempt {attempt}/{max_retries}, URL={url}")
                await asyncio.sleep(2 * (attempt + 1))  # Увеличенная задержка между попытками
            response = await client.get(url, timeout=request_timeout)
            if attempt == 0:
                print(f"[PLAYER] {label}: HTTP {response.status_code}, URL={url}")
            response.raise_for_status()
            data = response.json()
            if attempt == 0:
                print(f"[PLAYER] {label}: response type={type(data).__name__}, size={len(str(data)) if data else 0}")
            return data
        except httpx.TimeoutException:
            if attempt == 0:
                print(f"[PLAYER] {label}: Timeout error")
            if attempt < max_retries:
                continue
            return default_value
        except httpx.RequestError as e:
            if attempt == 0:
                print(f"[PLAYER] {label}: Request error - {e}")
            if attempt < max_retries:
                continue
            return default_value
        except Exception as e:
            if attempt == 0:
                print(f"[PLAYER] {label}: Unexpected error - {e}")
            if attempt < max_retries:
                continue
            return default_value


async def fetch_year_activity_matches(client, player_id, days=ACTIVITY_DAYS, page_limit=100, max_pages=20):
    matches = []
    seen_ids = set()

    for page in range(max_pages):
        offset = page * page_limit
        payload = await fetch_json(
            client,
            f"{OPEN_DOTA_API}/players/{player_id}/matches?limit={page_limit}&offset={offset}&significant=0&date={days}",
            [],
            label=f"activity_year_{page + 1}",
            max_retries=1,
        )
        if not isinstance(payload, list) or not payload:
            break

        for row in payload:
            if not isinstance(row, dict):
                continue
            match_id = to_int(row.get("match_id"), 0)
            if match_id > 0 and match_id in seen_ids:
                continue
            if match_id > 0:
                seen_ids.add(match_id)
            matches.append(row)

        if len(payload) < page_limit:
            break

    return matches


async def fetch_match_at_offset(client, player_id, offset):
    payload = await fetch_json(
        client,
        f"{OPEN_DOTA_API}/players/{player_id}/matches?limit=1&offset={offset}&significant=0",
        [],
    )
    if isinstance(payload, list) and payload:
        return payload[0]
    return None


async def resolve_first_match_date(client, player_id, total_matches, recent_matches):
    # OpenDota ignores sort/ascending on /players/{id}/matches and always answers
    # newest-first, so the oldest match has to be addressed by offset. Asking for
    # sorted-ascending here used to hand back the *latest* match instead.
    if total_matches > 0:
        try:
            oldest = await fetch_match_at_offset(client, player_id, total_matches - 1)
            if oldest:
                oldest_timestamp = to_int(oldest.get("start_time"), 0)
                if oldest_timestamp > 0:
                    return format_match_date(oldest_timestamp)
        except Exception:
            pass

    # Fallback: oldest match inside the recent feed we already hold.
    recent_timestamps = [to_int(m.get("start_time"), 0) for m in recent_matches if to_int(m.get("start_time"), 0) > 0]
    if recent_timestamps:
        return format_match_date(min(recent_timestamps))

    return "Неизвестно"


def prettify_hero_name(hero_name):
    return str(hero_name or "unknown").replace("_", " ").title()


HERO_ROLE_HINTS = {
    "nevermore": "Mid Lane",
    "shadow_fiend": "Mid Lane",
    "invoker": "Mid Lane",
    "puck": "Mid Lane",
    "void_spirit": "Mid Lane",
    "storm_spirit": "Mid Lane",
    "ember_spirit": "Mid Lane",
    "sniper": "Mid Lane",
    "huskar": "Mid Lane",
    "phantom_assassin": "Safe Lane",
    "juggernaut": "Safe Lane",
    "terrorblade": "Safe Lane",
    "ursa": "Safe Lane",
    "slark": "Safe Lane",
    "monkey_king": "Safe Lane",
    "axe": "Off Lane",
    "mars": "Off Lane",
    "magnataur": "Off Lane",
    "bristleback": "Off Lane",
    "centaur": "Off Lane",
    "tidehunter": "Off Lane",
    "earthshaker": "Roam/Support",
    "pudge": "Roam/Support",
    "lion": "Support",
    "rubick": "Support",
    "witch_doctor": "Support",
    "crystal_maiden": "Support",
    "undying": "Support",
    "techies": "Support",
    "hoodwink": "Support",
    # Герои с устойчивой ролью. Те, кого мета регулярно двигает между позициями
    # (например Nature's Prophet), намеренно не перечислены - для них честнее
    # показать общий план, чем уверенно назвать одну позицию.
    "faceless_void": "Safe Lane",
    "spectre": "Safe Lane",
    "luna": "Safe Lane",
    "medusa": "Safe Lane",
    "lifestealer": "Safe Lane",
    "sven": "Safe Lane",
    "gyrocopter": "Safe Lane",
    "drow_ranger": "Safe Lane",
    "troll_warlord": "Safe Lane",
    "naga_siren": "Safe Lane",
    "chaos_knight": "Safe Lane",
    "skeleton_king": "Safe Lane",
    "lina": "Mid Lane",
    "queenofpain": "Mid Lane",
    "zuus": "Mid Lane",
    "death_prophet": "Mid Lane",
    "templar_assassin": "Mid Lane",
    "leshrac": "Mid Lane",
    "arc_warden": "Mid Lane",
    "dark_seer": "Off Lane",
    "beastmaster": "Off Lane",
    "abyssal_underlord": "Off Lane",
    "legion_commander": "Off Lane",
    "night_stalker": "Off Lane",
    "doom_bringer": "Off Lane",
    "shredder": "Off Lane",
    "brewmaster": "Off Lane",
    "dawnbreaker": "Off Lane",
    "primal_beast": "Off Lane",
    "slardar": "Off Lane",
    "enigma": "Off Lane",
    "dazzle": "Support",
    "shadow_shaman": "Support",
    "warlock": "Support",
    "oracle": "Support",
    "disruptor": "Support",
    "jakiro": "Support",
    "ancient_apparition": "Support",
    "bane": "Support",
    "wisp": "Support",
    "keeper_of_the_light": "Support",
    "grimstroke": "Support",
    "winter_wyvern": "Support",
    "shadow_demon": "Support",
    "skywrath_mage": "Support",
    "lich": "Support",
    "abaddon": "Support",
    "snapfire": "Support",
    "nyx_assassin": "Roam/Support",
    "spirit_breaker": "Roam/Support",
    "mirana": "Roam/Support",
    "rattletrap": "Roam/Support",
    "tusk": "Roam/Support",
    "bounty_hunter": "Roam/Support",
    "sand_king": "Roam/Support",
}

# Руководство по роли для панели гайдов. Советы намеренно ролевые, а не
# заточенные под конкретного героя: придумывать пер-геройские билды на 120+
# героев значило бы выдавать домыслы за факты.
HERO_GUIDE_BY_ROLE = {
    "Mid Lane": {
        "plan": "Контролируй руны и создавай темп после 6-8 минуты",
        "early": "Держи волну ближе к своей вышке при плохом матчапе, забирай обе руны",
        "items": "Bottle -> предмет на мобильность -> первый боевой слот",
        "mistake": "Уход в фарм после 10 минуты: мид без давления бесполезен команде",
    },
    "Safe Lane": {
        "plan": "Не дерись без ключевого слота, играй от фарм-паттерна",
        "early": "Линия -> ближайший кемп -> линия; не теряй волны ради чужих драк",
        "items": "Ускорение фарма -> первый боевой слот -> отмена контроля",
        "mistake": "Драки на чужих таймингах вместо своего ключевого предмета",
    },
    "Off Lane": {
        "plan": "Ломай линию давлением, после первого предмета играй на инициацию",
        "early": "Разменивай ХП, отжимай кемпы врага, тяни за собой саппорта",
        "items": "Живучесть -> инициация -> аура на команду",
        "mistake": "Соло-дайвы без команды: инициация без поддержки просто отдаёт темп",
    },
    "Support": {
        "plan": "Вижен и размены, тело не отдавать до кор-тайминга",
        "early": "Ставь варды до спавна рун, стакай кемпы своему кору",
        "items": "Расходники и вижен -> спасение кора -> усиление на драки",
        "mistake": "Экономия на вардах: карта без вижена стоит команде драк, а не золота",
    },
    "Roam/Support": {
        "plan": "Делай спейс смоками и гангами, конвертируй килл в объект",
        "early": "Ищи размены на чужой линии, но не пропадай с карты надолго",
        "items": "Мобильность -> контроль -> живучесть под инициацию",
        "mistake": "Ганги без конверсии: килл без вышки или Рошана не даёт ничего",
    },
}
HERO_GUIDE_DEFAULT = {
    "plan": "Держи узкий пул и конвертируй выигранные драки в объекты",
    "early": "Первые 10 минут проще: линия, тайминг первого слота, потом драка",
    "items": "Сначала слот под свою задачу, потом реакция на драфт врага",
    "mistake": "Расширение пула во время просадки: это удлиняет лузстрик",
}


def snapshot_has_real_data(snapshot):
    if not isinstance(snapshot, dict):
        return False
    return any(
        [
            to_int(snapshot.get("total_matches"), 0) > 0,
            to_int(snapshot.get("matches"), 0) > 0,
            bool(snapshot.get("top_heroes")),
            bool(snapshot.get("most_played_heroes")),
            bool(snapshot.get("matches")),
        ]
    )


def collect_coach_heroes(snapshot):
    combined = {}
    for source_name in ("top_heroes", "most_played_heroes"):
        rows = snapshot.get(source_name) if isinstance(snapshot.get(source_name), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            hero_name = str(row.get("hero_name") or "").strip()
            if not hero_name or hero_name == "unknown":
                continue
            current = combined.setdefault(
                hero_name,
                {
                    "hero_name": hero_name,
                    "games": 0,
                    "wins": 0,
                    "winrate": 0.0,
                    "all_time_games": 0,
                    "all_time_winrate": 0.0,
                    "sample": "",
                    "sources": set(),
                },
            )
            games = to_int(row.get("games"), 0)
            wins = to_int(row.get("wins"), round(games * (to_float(row.get("winrate"), 0) / 100)))
            winrate = to_float(row.get("winrate"), 0)

            if source_name == "most_played_heroes":
                current["all_time_games"] = max(to_int(current.get("all_time_games"), 0), games)
                current["all_time_winrate"] = max(to_float(current.get("all_time_winrate"), 0), winrate)

            # Prefer the selected match window for tactical advice; all-time data is only a backup.
            if source_name == "top_heroes" or "top_heroes" not in current["sources"]:
                current["games"] = games
                current["wins"] = wins
                current["winrate"] = winrate
                current["sample"] = "окно" if source_name == "top_heroes" else "вся история"
            current["sources"].add(source_name)

    heroes = []
    for hero in combined.values():
        games = to_int(hero.get("games"), 0)
        winrate = to_float(hero.get("winrate"), 0)
        score = winrate + min(games, 30) * 0.8
        if games < 3:
            score -= 8
        hero["score"] = round(score, 2)
        hero["role_hint"] = HERO_ROLE_HINTS.get(hero["hero_name"], "")
        heroes.append(hero)

    heroes.sort(key=lambda item: (to_float(item.get("score"), 0), to_int(item.get("games"), 0)), reverse=True)
    return heroes


def coach_hero_line(heroes, limit=3):
    if not heroes:
        return "нет надежного героя в данных"
    parts = []
    for hero in heroes[:limit]:
        name = prettify_hero_name(hero.get("hero_name"))
        wr = to_float(hero.get("winrate"), 0)
        games = to_int(hero.get("games"), 0)
        parts.append(f"{name} {wr:g}% за {games} игр")
    return ", ".join(parts)


def coach_recent_form(snapshot):
    trend = snapshot.get("win_trend") if isinstance(snapshot.get("win_trend"), list) else []
    if not trend:
        return "тренд побед не пришел из API"
    last = trend[-10:]
    wins = sum(1 for point in last if to_int(point, 0) > 0)
    losses = len(last) - wins
    if len(last) >= 4 and all(to_int(point, 0) > 0 for point in last[-3:]):
        status = "идет винстрик, можно закреплять пул"
    elif len(last) >= 4 and all(to_int(point, 0) < 0 for point in last[-3:]):
        status = "лузстрик, надо снизить риск и играть проще"
    elif wins >= losses:
        status = "форма живая, но важно не разбрасываться героями"
    else:
        status = "форма просела, нужен более узкий план на 3-5 игр"
    return f"{wins}-{losses} за последние {len(last)} матчей, {status}"


def coach_stat_diagnosis(snapshot):
    recent_wr = to_float(snapshot.get("recent_wr"), 0)
    avg_deaths = to_float(snapshot.get("avg_deaths"), 0)
    avg_gpm = to_int(snapshot.get("avg_gpm"), 0)
    avg_xpm = to_int(snapshot.get("avg_xpm"), 0)
    avg_kda = to_float(snapshot.get("avg_kda"), 0)

    notes = []
    if recent_wr >= 55:
        notes.append("винрейт окна сильный: можно играть от своих таймингов, а не от хаоса команды")
    elif recent_wr and recent_wr < 48:
        notes.append("винрейт окна красный: первые 15 минут нужно упростить, меньше авантюрных драк")
    else:
        notes.append("винрейт окна средний: решают детали по смертям и конверсии выигранных драк")

    if avg_deaths >= 8:
        notes.append(f"{avg_deaths:g} смертей в среднем - главный слив темпа, особенно после первого важного предмета")
    elif avg_deaths <= 5 and avg_deaths > 0:
        notes.append(f"{avg_deaths:g} смертей - нормальная база, можно добавлять агрессию через вижен/смоки")

    if avg_gpm > 0 and avg_gpm < 480:
        notes.append(f"GPM {avg_gpm}: мало циклов фарма между драками, теряешь волны и нейтралов")
    elif avg_gpm >= 560:
        notes.append(f"GPM {avg_gpm}: фарм-темп хороший, задача - конвертировать его в вышки/Рошана")

    if avg_xpm > 0 and avg_xpm < 600:
        notes.append(f"XPM {avg_xpm}: часто выпадаешь с карты после смерти или не добираешь линии")

    if avg_kda >= 3:
        notes.append(f"KDA {avg_kda:g}: импакт в драках есть, не ломай его лишним дайвом")
    elif avg_kda > 0 and avg_kda < 2:
        notes.append(f"KDA {avg_kda:g}: драки пока дорогие, нужен вход вторым темпом")

    return notes[:5]


def infer_best_role_from_heroes(heroes):
    role_scores = defaultdict(lambda: {"score": 0.0, "heroes": []})
    for hero in heroes:
        role = hero.get("role_hint")
        if not role:
            continue
        role_scores[role]["score"] += to_float(hero.get("score"), 0)
        role_scores[role]["heroes"].append(hero)
    if not role_scores:
        return None
    role, data = max(role_scores.items(), key=lambda item: item[1]["score"])
    data["label"] = role
    return data


def coach_role_matches(hero_role, target_role):
    hero_role = str(hero_role or "").lower()
    target_role = str(target_role or "").lower()
    if not hero_role or not target_role:
        return False
    return hero_role in target_role or target_role in hero_role or any(part and part in target_role for part in hero_role.split("/"))


def local_general_coach_response(snapshot):
    if not snapshot_has_real_data(snapshot):
        return "Сначала загрузи профиль игрока: без матчей я не буду гадать по воздуху."

    recent_wr = to_float(snapshot.get("recent_wr"), 0)
    total_wr = to_float(snapshot.get("total_wr"), 0)
    avg_deaths = to_float(snapshot.get("avg_deaths"), 0)
    avg_gpm = to_int(snapshot.get("avg_gpm"), 0)
    avg_xpm = to_int(snapshot.get("avg_xpm"), 0)
    avg_kda = to_float(snapshot.get("avg_kda"), 0)
    heroes = collect_coach_heroes(snapshot)
    strong_heroes = [hero for hero in heroes if to_float(hero.get("winrate"), 0) >= 52 and to_int(hero.get("games"), 0) >= 2]
    risky_heroes = [hero for hero in heroes if to_float(hero.get("winrate"), 0) < 48 and to_int(hero.get("games"), 0) >= 3]
    core_pool = strong_heroes or heroes[:3]
    best_lane = snapshot.get("best_lane") if isinstance(snapshot.get("best_lane"), dict) else None
    inferred_role = infer_best_role_from_heroes(core_pool)
    lane_text = ""
    if best_lane and best_lane.get("label"):
        lane_text = f"{best_lane.get('label')} ({best_lane.get('winrate', 0)}% за {best_lane.get('games', 0)} игр)"
    elif inferred_role:
        lane_text = f"{inferred_role['label']} по пулу героев: {coach_hero_line(inferred_role.get('heroes', []), 2)}"
    else:
        lane_text = "роль не определена надежно, опираемся на геройский пул"

    diagnostics = coach_stat_diagnosis(snapshot)
    plan = []
    if avg_deaths >= 7:
        plan.append("до 20 минуты не заходи первым без вижена: твоя смерть обнуляет спейс и ломает тайминги")
    if avg_gpm > 0 and avg_gpm < 500:
        plan.append("после каждой драки делай один фарм-цикл: линия -> ближайший кемп -> линия, только потом новый файт")
    if avg_xpm > 0 and avg_xpm < 600:
        plan.append("после респауна сразу занимай свободную линию, иначе проседаешь по уровню и теряешь драку на кнопках")
    if recent_wr >= 55:
        plan.append("не расширяй пул: спамь сильных героев и закрепляй первые 2 ключевых тайминга")
    if not plan:
        plan.append("держи узкий пул 2-3 героя и смотри не на KDA, а на конверсию: килл -> вышка/Рошан/варды")

    risky_line = coach_hero_line(risky_heroes, 2) if risky_heroes else "явной красной зоны по героям нет"
    lines = [
        "Полная аналитика:",
        f"- Окно: WR {recent_wr:g}% при общем WR {total_wr:g}%, KDA {avg_kda:g}, GPM/XPM {avg_gpm}/{avg_xpm}, смертей {avg_deaths:g}.",
        f"- Форма: {coach_recent_form(snapshot)}.",
        f"- Сильный пул: {coach_hero_line(core_pool, 3)}. Играй через них, тут уже есть база для побед.",
        f"- Роль/фокус: {lane_text}.",
        f"- Риск-пул: {risky_line}. Если герой тут есть, не спамь его до фикса ошибок.",
    ]
    for note in diagnostics[:3]:
        lines.append(f"- Диагноз: {note}.")
    for item in plan[:3]:
        lines.append(f"- План: {item}.")
    return "\n".join(lines)


def local_last_match_response(snapshot):
    matches = snapshot.get("matches") if isinstance(snapshot.get("matches"), list) else []
    if not matches:
        return "Не вижу данных последнего матча. Сначала загрузите профиль игрока."

    last_match = matches[0]
    hero = prettify_hero_name(last_match.get("hero_name"))
    kills = to_int(last_match.get("kills"), 0)
    deaths = to_int(last_match.get("deaths"), 0)
    assists = to_int(last_match.get("assists"), 0)
    impact = kills + assists - deaths
    items = [item for item in last_match.get("items", []) if item and "Item " not in str(item)]
    mode = last_match.get("game_mode_label") or "Unknown"
    match_date = last_match.get("match_date") or "-"

    micro_tips = []
    macro_tips = []

    if deaths >= 8:
        micro_tips.append("снизить агрессию без информации по карте")
    if kills <= 4:
        micro_tips.append("добавить активные перемещения с саппортом под смоки")
    if assists <= 8:
        macro_tips.append("чаще подключаться к командным файтам на ключевых таймингах")
    if impact < 10:
        macro_tips.append("сфокусироваться на objective-игре после выигранной драки")
    if not macro_tips:
        macro_tips.append("после каждого фрага конвертировать преимущество в вышку/Рошана")
    if not micro_tips:
        micro_tips.append("сохранять текущую механику, усиливать позиционку в лейте")

    build_line = ", ".join(items[:6]) if items else "сборка недоступна в данных"

    return (
        "Разбор последней игры:\n"
        f"- Матч: {hero}, режим {mode}, K/D/A {kills}/{deaths}/{assists}, импакт {impact}, дата {match_date}.\n"
        f"- Сборка: {build_line}.\n"
        f"- Микро: {', '.join(micro_tips[:2])}.\n"
        f"- Макро: {', '.join(macro_tips[:2])}."
    )


def local_position_response(snapshot):
    if not snapshot_has_real_data(snapshot):
        return "Сначала загрузи профиль игрока: без матчей роль не определить."

    best_lane = snapshot.get("best_lane") if isinstance(snapshot.get("best_lane"), dict) else None
    lane_breakdown = snapshot.get("lane_breakdown") if isinstance(snapshot.get("lane_breakdown"), list) else []
    heroes = collect_coach_heroes(snapshot)

    if not best_lane and lane_breakdown:
        best_lane = lane_breakdown[0]

    strong_role_heroes = [
        hero
        for hero in heroes
        if to_float(hero.get("winrate"), 0) >= 50 and to_int(hero.get("games"), 0) >= 2
    ]
    inferred_role = infer_best_role_from_heroes(strong_role_heroes or heroes)

    if best_lane:
        lane_label = best_lane.get("label", "Unknown")
        lane_wr = best_lane.get("winrate", 0)
        lane_games = best_lane.get("games", 0)
        header_line = f"{lane_label}: {lane_wr}% за {lane_games} игр"
    elif inferred_role:
        lane_label = inferred_role["label"]
        header_line = f"{lane_label}: вывод по героям, потому что API не дал стабильных ролей"
    else:
        lane_label = "узкий геройский пул"
        header_line = "роль не определена: играй от 2-3 лучших героев, пока не появится больше данных по линиям"

    role_heroes = [hero for hero in heroes if coach_role_matches(hero.get("role_hint"), lane_label)]
    if not role_heroes and inferred_role:
        role_heroes = inferred_role.get("heroes", [])
    candidate_heroes = role_heroes or heroes

    hero_recommendations = []
    for hero in candidate_heroes:
        games = to_int(hero.get("games"), 0)
        winrate = to_float(hero.get("winrate"), 0)
        if games >= 2 and winrate >= 50:
            hero_recommendations.append(prettify_hero_name(hero.get("hero_name")))

    hero_line = ", ".join(hero_recommendations[:3]) if hero_recommendations else coach_hero_line(candidate_heroes, 3)
    style_tip = "играй проще первые 10 минут: линия, тайминг первого слота, потом драка под вижен"
    if "Support" in lane_label or "Roam" in lane_label:
        style_tip = "делай спейс через смоки и вижен, но не отдавай тело первым без кор-тайминга"
    elif "Mid" in lane_label:
        style_tip = "контролируй руны и первый активный тайминг: после 6-8 минуты ты обязан создавать темп"
    elif "Safe" in lane_label:
        style_tip = "не дерись без ключевого слота: твой макроконтроль - фарм-паттерн и безопасные волны"
    elif "Off" in lane_label:
        style_tip = "ломай линию давлением, но после первого предмета играй на инициацию, а не на соло-дайвы"

    return (
        "Лучшая позиция и фокус:\n"
        f"- Вердикт: {header_line}.\n"
        f"- Герои под фокус: {hero_line}.\n"
        f"- Почему: твой лучший сигнал сейчас идет от героев/роли, а не от абстрактной статы.\n"
        f"- План на 5 игр: {style_tip}.\n"
        "- Контрольный KPI: меньше лишних смертей до 20 минуты и минимум один объект после выигранной драки."
    )


def local_meta_main_response(snapshot):
    # Simple meta pool for demo mode on commission presentation.
    meta_pool = [
        "puck",
        "shadow_fiend",
        "mars",
        "primal_beast",
        "tiny",
        "terrorblade",
        "windrunner",
        "lion",
        "hoodwink",
        "monkey_king",
    ]

    top_heroes = collect_coach_heroes(snapshot)
    top_names = [hero.get("hero_name") for hero in top_heroes if hero.get("hero_name")]
    comfort_meta = [name for name in top_names if name in meta_pool]
    comfort_meta_line = ", ".join(prettify_hero_name(hero) for hero in comfort_meta[:3]) if comfort_meta else "пока нет явных пересечений"

    main_candidates = []
    for hero in top_heroes:
        games = to_int(hero.get("games"), 0)
        wr = to_float(hero.get("winrate"), 0)
        if games >= 2 and wr >= 52:
            main_candidates.append(prettify_hero_name(hero.get("hero_name")))

    main_line = ", ".join(main_candidates[:2]) if main_candidates else "выберите 1-2 героя с наибольшим винрейтом из топ-3"
    meta_line = ", ".join(prettify_hero_name(hero) for hero in meta_pool[:5])

    return (
        "Мета и кого мейнить:\n"
        f"- Текущие герои меты (пример): {meta_line}.\n"
        f"- Совпадение с вашим комфорт-пулом: {comfort_meta_line}.\n"
        f"- Кого мейнить: {main_line}.\n"
        "- План: основной пул 2 героя + 1 запасной под плохой драфт."
    )


def build_local_coach_response(prompt, snapshot, selected_prompt_id=""):
    prompt_id = str(selected_prompt_id or "").strip()
    if prompt_id == "last_match_review":
        return local_last_match_response(snapshot)
    if prompt_id == "weakness_plan":
        return local_general_coach_response(snapshot)
    if prompt_id == "best_role_focus":
        return local_position_response(snapshot)
    if prompt_id == "meta_main":
        return local_meta_main_response(snapshot)
    if prompt_id == "full_analytics":
        return local_general_coach_response(snapshot)

    prompt_lower = str(prompt or "").lower()

    if any(token in prompt_lower for token in ["привет", "прив", "здаров", "салам", "hello", "hi"]):
        return (
            "Привет. Я на связи.\n"
            "- Можешь спросить про макро, микро, героя, сборку или последний матч.\n"
            "- Если хочешь жесткий разбор, жми одну из кнопок выше."
        )
    if any(token in prompt_lower for token in ["послед", "last game", "last match"]):
        return local_last_match_response(snapshot)
    if any(token in prompt_lower for token in ["слаб", "исправ", "ошиб", "weakness"]):
        return local_general_coach_response(snapshot)
    if any(token in prompt_lower for token in ["позиц", "role", "lane"]):
        return local_position_response(snapshot)
    if any(token in prompt_lower for token in ["мет", "main", "мейн", "hero pool"]):
        return local_meta_main_response(snapshot)
    if any(token in prompt_lower for token in ["как", "что", "почему", "зачем", "можно", "стоит", "?"]):
        return (
            "Отвечу как тренер, коротко.\n"
            f"- По твоему вопросу: {str(prompt or '').strip()[:140]}\n"
            "- Если речь про игру: смотри на тайминги, позиционку и цену каждой драки.\n"
            "- Дай конкретику: герой, роль, минута или ситуация, и я разберу уже точечно."
        )
    clean_prompt = str(prompt or "").strip()
    return (
        "Слышу тебя.\n"
        f"- По сообщению: {clean_prompt[:140] if clean_prompt else 'без конкретики'}.\n"
        "- Если это не про Доту/CS2, окей: выдохнул, собрался, вернулся в лобби с холодной головой.\n"
        "- Хочешь пользы прямо сейчас: напиши героя, роль и момент матча, где просел. Разберу как тренер."
    )


async def call_openai_coach(prompt, snapshot, coach_context=None):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    conversation = []
    if isinstance(coach_context, dict):
        for row in coach_context.get("conversation", [])[-10:]:
            if not isinstance(row, dict):
                continue
            role = "assistant" if row.get("role") == "assistant" else "user"
            content = str(row.get("content") or "").strip()
            if content:
                conversation.append({"role": role, "content": content[:1000]})

    selected_prompt_id = ""
    if isinstance(coach_context, dict):
        selected_prompt_id = str(coach_context.get("selected_prompt_id") or "").strip()
    system_text = (
        "Ты Arena AI Coach, элитный аналитик Dota 2 и CS2. Отвечай на русском, как живой тренер, без воды. "
        "Не выдавай шаблон: привязывай каждый совет к цифрам из JSON, сильным героям, роли, последним матчам и таймингам. "
        "Стиль: лаконично, жестко, но конструктивно; термины: позиционка, тайминги, макроконтроль, спейс, драфт. "
        "Если вопрос вне игры, ответь коротко как тиммейт и верни к дисциплине. "
        "Формат: 5-8 коротких пунктов, без огромных простыней."
    )
    user_text = (
        f"ID пресета: {selected_prompt_id or 'free_chat'}\n"
        f"Запрос пользователя: {prompt}\n"
        f"Статистика игрока JSON:\n{json.dumps(snapshot, ensure_ascii=False)[:7000]}"
    )
    messages = [{"role": "system", "content": system_text}]
    messages.extend(conversation)
    if not messages or messages[-1].get("role") != "user":
        messages.append({"role": "user", "content": user_text})
    else:
        messages.append({"role": "user", "content": user_text})

    payload = {
        "model": model,
        "temperature": 0.4,
        "max_tokens": 500,
        "messages": messages,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            response = await client.post(
                f"{api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices") if isinstance(data, dict) else None
            if isinstance(choices, list) and choices:
                message = choices[0].get("message", {})
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
    except Exception as error:
        print(f"[OpenAI Coach error] {type(error).__name__}: {error}")
        return None

    return None


async def call_gemini_coach(prompt, snapshot, coach_context=None):
    api_key = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        return None

    api_base = os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

    conversation = []
    selected_prompt_id = ""
    if coach_context and isinstance(coach_context, dict):
        selected_prompt_id = str(coach_context.get("selected_prompt_id") or "").strip()
        conv = coach_context.get("conversation", [])
        if isinstance(conv, list):
            for row in conv[-10:]:
                if isinstance(row, dict) and row.get("role") in ("user", "assistant"):
                    role = "model" if row["role"] == "assistant" else "user"
                    content_text = str(row.get("content", ""))[:1000]
                    if content_text:
                        conversation.append({"role": role, "parts": [{"text": content_text}]})

    prompt_clean = str(prompt or "").strip()
    if conversation and conversation[-1]["role"] == "user":
        last_text = conversation[-1]["parts"][0].get("text", "") if conversation[-1].get("parts") else ""
        if str(last_text).strip() == prompt_clean:
            conversation.pop()

    snapshot_text = json.dumps(snapshot, ensure_ascii=False)[:7000] if snapshot else "{}"
    current_request = (
        f"ID пресета: {selected_prompt_id or 'free_chat'}\n"
        f"Запрос пользователя: {prompt_clean}\n"
        f"Данные игрока JSON:\n{snapshot_text}\n\n"
        "Сделай ответ персональным: используй сильных героев, слабые метрики, роль/линию, последние матчи и конкретный план."
    )
    conversation.append({"role": "user", "parts": [{"text": current_request}]})

    system_text = (
        "Ты Arena AI Coach, элитный аналитик Dota 2 и CS2. Отвечай на русском. "
        "Не пиши шаблонные советы: каждый вывод связывай с цифрами и героями из JSON. "
        "Если выбран пресет full_analytics, дай макро/микро/стабильность/пул героев. "
        "Если best_role_focus, выбери лучшую роль; если ролей мало, сделай вывод по сильным героям и честно так скажи. "
        "Тон: киберспортивно, прямо, без лести. Формат: короткий заголовок и 5-8 пунктов. "
        "Не возвращай JSON."
    )

    payload = {
        "systemInstruction": {
            "parts": [{"text": system_text}],
        },
        "contents": conversation,
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 2048,
        },
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
                response = await client.post(
                    f"{api_base}/models/{model}:generateContent?key={urllib.parse.quote_plus(api_key)}",
                    headers={"Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                candidates = data.get("candidates") if isinstance(data, dict) else None
                if isinstance(candidates, list) and candidates:
                    content_obj = candidates[0].get("content", {})
                    parts = content_obj.get("parts", []) if isinstance(content_obj, dict) else []
                    text_parts = [part.get("text") for part in parts if isinstance(part, dict) and part.get("text")]
                    if text_parts:
                        return "\n".join(text_parts).strip()
                break
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (503, 429) and attempt < 2:
                await asyncio.sleep((attempt + 1) * 3)
                continue
            print(f"[Gemini API error] {type(e).__name__}: {e}")
        except Exception as e:
            print(f"[Gemini API error] {type(e).__name__}: {e}")

    return None



async def call_llm_coach(prompt, snapshot, coach_context=None):
    try:
        gemini_answer = await call_gemini_coach(prompt, snapshot, coach_context=coach_context)
        if gemini_answer:
            return {
                "answer": gemini_answer,
                "source": "gemini",
            }
    except Exception as error:
        print(f"[Coach LLM fallback] Gemini failed: {type(error).__name__}: {error}")

    try:
        openai_answer = await call_openai_coach(prompt, snapshot, coach_context=coach_context)
        if openai_answer:
            return {
                "answer": openai_answer,
                "source": "llm",
            }
    except Exception as error:
        print(f"[Coach LLM fallback] OpenAI failed: {type(error).__name__}: {error}")

    return None


def parse_steam_id64_from_claimed_id(claimed_id):
    value = str(claimed_id or "").strip()
    if not value:
        return ""

    match = re.search(r"/openid/id/(\d{17,20})", value, flags=re.IGNORECASE)
    if match:
        return match.group(1)

    match = re.search(r"/profiles/(\d{17,20})", value, flags=re.IGNORECASE)
    if match:
        return match.group(1)

    return ""


def extract_xml_tag(xml_text, tag_name):
    if not xml_text:
        return ""

    cdata_pattern = rf"<{tag_name}><!\[CDATA\[(.*?)\]\]></{tag_name}>"
    plain_pattern = rf"<{tag_name}>(.*?)</{tag_name}>"

    cdata_match = re.search(cdata_pattern, xml_text, flags=re.IGNORECASE | re.DOTALL)
    if cdata_match:
        return str(cdata_match.group(1)).strip()

    plain_match = re.search(plain_pattern, xml_text, flags=re.IGNORECASE | re.DOTALL)
    if plain_match:
        return str(plain_match.group(1)).strip()

    return ""


async def fetch_steam_public_profile(client, steam_id64):
    steam_id = str(steam_id64 or "").strip()
    if not steam_id:
        return {}

    profile_xml_url = f"https://steamcommunity.com/profiles/{steam_id}/?xml=1"
    try:
        response = await client.get(
            profile_xml_url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/xml,text/xml,text/html,*/*",
            },
        )
        response.raise_for_status()
        xml_text = response.text
        persona_name = extract_xml_tag(xml_text, "steamID")
        avatar = extract_xml_tag(xml_text, "avatarFull") or extract_xml_tag(xml_text, "avatarMedium")
        return {
            "persona_name": persona_name or "",
            "avatar": avatar or "",
        }
    except Exception:
        return {}


async def verify_steam_openid(request: Request):
    query_params = dict(request.query_params)
    if not query_params:
        return {"ok": False}

    verification_payload = {key: value for key, value in query_params.items() if key.startswith("openid.")}
    if not verification_payload:
        return {"ok": False}

    verification_payload["openid.mode"] = "check_authentication"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
            verification = await client.post(
                STEAM_OPENID_ENDPOINT,
                data=verification_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            verification.raise_for_status()
            is_valid = "is_valid:true" in verification.text
            return {
                "ok": is_valid,
                "claimed_id": query_params.get("openid.claimed_id", ""),
            }
    except Exception:
        return {"ok": False}


def session_steam_id(request: Request) -> str:
    session_user = request.session.get("steam_user") if hasattr(request, "session") else None
    if not isinstance(session_user, dict):
        return ""
    return str(session_user.get("steam_id64") or "").strip()


async def current_steam_user(request: Request) -> Optional[Dict[str, Any]]:
    steam_id64 = session_steam_id(request)
    if not steam_id64:
        return None

    # Свежий профиль берём из базы; если она недоступна, показываем то, что
    # осталось в сессии с момента входа.
    stored = await db.get_user_by_steam_id(steam_id64)
    return stored or request.session.get("steam_user")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    steam_user = await current_steam_user(request)
    return templates.TemplateResponse(request, "home.html", {"steam_user": steam_user})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/auth/steam/login")
async def auth_steam_login(request: Request):
    base_url = str(request.base_url).rstrip("/")
    return_to = f"{base_url}/auth/steam/callback"

    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": return_to,
        "openid.realm": base_url,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }

    redirect_url = f"{STEAM_OPENID_ENDPOINT}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=redirect_url, status_code=302)


@app.get("/auth/steam/callback")
async def auth_steam_callback(request: Request):
    verification = await verify_steam_openid(request)
    if not verification.get("ok"):
        return RedirectResponse(url="/?auth=failed", status_code=302)

    steam_id64 = parse_steam_id64_from_claimed_id(verification.get("claimed_id"))
    account_id = steam64_to_account_id(steam_id64)
    if not steam_id64 or not account_id:
        return RedirectResponse(url="/?auth=failed", status_code=302)

    persona_name = ""
    avatar = ""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=6.0)) as client:
            profile = await fetch_steam_public_profile(client, steam_id64)
            persona_name = profile.get("persona_name", "")
            avatar = profile.get("avatar", "")
    except Exception:
        pass

    stored = await db.upsert_user(steam_id64, account_id, persona_name, avatar)
    if stored:
        # Профиль лежит в базе, в cookie уходит только идентификатор. Сессионная
        # cookie подписана, но не зашифрована - её содержимое читается кем угодно,
        # поэтому держим там минимум.
        request.session["steam_user"] = {"steam_id64": steam_id64}
    else:
        # Без базы восстанавливать профиль неоткуда - оставляем его в сессии.
        request.session["steam_user"] = {
            "steam_id64": steam_id64,
            "account_id": account_id,
            "persona_name": persona_name or f"Steam {steam_id64}",
            "avatar": avatar,
        }
    return RedirectResponse(url="/", status_code=302)


@app.get("/auth/logout")
async def auth_logout(request: Request):
    if hasattr(request, "session"):
        request.session.pop("steam_user", None)
    return RedirectResponse(url="/", status_code=302)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return HTMLResponse(content="", status_code=204)


@app.get("/health", include_in_schema=False)
async def health():
    # Cheap endpoint for platform/container health checks - no templates, no APIs.
    # Deliberately still "ok" without a database: the dashboard works without one,
    # so a failing database must not make the platform recycle the container.
    return {"status": "ok", "database": db.is_ready()}


@app.get("/api/stats")
async def database_stats():
    # Aggregate counts only - never rows, so this exposes no personal data.
    return await db.get_stats()


@app.get("/api/player/resolve")
async def resolve_player_input(request: Request, query: str = ""):
    normalized_query = str(query or "").strip()
    if not normalized_query:
        return {"error": "Введите Steam ID, ссылку профиля или ник"}

    print(f"[RESOLVE] Processing query: {normalized_query}")
    steam_id64 = session_steam_id(request)

    direct_account_id = extract_account_id_from_input(normalized_query)
    if direct_account_id:
        print(f"[RESOLVE] Direct account ID found: {direct_account_id}")
        await db.record_search(normalized_query, direct_account_id, "direct", steam_id64)
        return {
            "account_id": direct_account_id,
            "source": "direct",
        }

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
        vanity_account_id = await resolve_steam_vanity_to_account_id(client, normalized_query)
        if vanity_account_id:
            print(f"[RESOLVE] Vanity account ID found: {vanity_account_id}")
            await db.record_search(normalized_query, vanity_account_id, "steam_vanity", steam_id64)
            return {
                "account_id": vanity_account_id,
                "source": "steam_vanity",
            }

        search_terms = build_search_terms(normalized_query)
        # Limit to first 2 terms to avoid too many requests
        for term in search_terms[:2]:
            try:
                print(f"[RESOLVE] Searching for term: {term}")
                encoded_term = urllib.parse.quote_plus(term)
                payload = await fetch_json(client, f"{OPEN_DOTA_API}/search?q={encoded_term}", [])
                match = pick_search_result(payload, term)
                if not match:
                    continue

                account_id = to_int(match.get("account_id"), 0)
                if account_id <= 0:
                    continue

                print(f"[RESOLVE] Found player: {match.get('personaname')} with ID: {account_id}")
                await db.record_search(normalized_query, account_id, "search", steam_id64)
                return {
                    "account_id": account_id,
                    "source": "search",
                    "personaname": match.get("personaname") or "",
                }
            except Exception as e:
                print(f"[RESOLVE] Error searching for {term}: {e}")
                continue

    return {"error": "Игрок не найден. Введите корректный URL, Steam ID или более точный ник."}


@app.post("/api/coach")
async def coach_response(request: Request, payload: CoachRequest):
    prompt = str(payload.prompt or "").strip()
    snapshot = payload.snapshot if isinstance(payload.snapshot, dict) else {}
    coach_context = {
        "selected_prompt_id": str(payload.selected_prompt_id or "").strip(),
        "prompt_origin": str(payload.prompt_origin or "").strip(),
        "conversation": payload.conversation if isinstance(payload.conversation, list) else [],
        "action_summary": payload.action_summary if isinstance(payload.action_summary, dict) else {},
    }

    if not prompt:
        return {"error": "Пустой запрос"}

    steam_id64 = session_steam_id(request)
    prompt_id = coach_context.get("selected_prompt_id", "")

    try:
        llm_result = await call_llm_coach(prompt, snapshot, coach_context=coach_context)
        if llm_result:
            await db.record_coach_exchange(prompt, llm_result.get("answer", ""), llm_result.get("source", ""), prompt_id, steam_id64)
            return llm_result
    except Exception as error:
        print(f"[Coach endpoint fallback] {type(error).__name__}: {error}")

    local_answer = build_local_coach_response(prompt, snapshot, prompt_id)
    await db.record_coach_exchange(prompt, local_answer, "local", prompt_id, steam_id64)
    return {
        "answer": local_answer,
        "source": "local",
    }


@app.get("/api/player/{player_id}")
async def get_player_data(player_id: int, stratz_only: bool = False):
    global hero_map, item_map

    print(f"[PLAYER] Fetching data for player_id: {player_id} (stratz_only={stratz_only})")
    
    # Validate player_id
    if player_id <= 0 or player_id > 999999999:
        print(f"[PLAYER] Invalid player_id: {player_id}")
        return json_payload_response({"error": "Неверный ID игрока"})

    cached_payload = get_cached_player_payload(player_id, stratz_only=stratz_only)
    if cached_payload:
        print(f"[PLAYER] Cache hit for player_id: {player_id}")
        return json_payload_response(cached_payload)

    # Второй уровень кеша: пережил перезапуск, поэтому после деплоя первый
    # посетитель не ждёт полного обхода внешних API.
    db_cached = await db.get_cached_player(player_id, stratz_only, CACHE_TTL)
    if db_cached:
        print(f"[PLAYER] DB cache hit for player_id: {player_id}")
        store_cached_player_payload(player_id, db_cached, stratz_only=stratz_only)
        return json_payload_response(db_cached)

    # Try Stratz API first if configured
    if is_stratz_configured():
        try:
            print(f"[PLAYER] Trying Stratz API...")
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0)) as stratz_client:
                stratz_data = await get_player_data_from_stratz(stratz_client, player_id)
                if isinstance(stratz_data, dict) and stratz_data.get("name"):
                    print(f"[PLAYER] Stratz API succeeded for {stratz_data.get('name')}")
                    store_cached_player_payload(player_id, stratz_data, stratz_only=stratz_only)
                    await db.store_cached_player(player_id, stratz_only, stratz_data)
                    return json_payload_response(stratz_data)
                else:
                    error = stratz_data.get("error", "Unknown") if isinstance(stratz_data, dict) else "None"
                    print(f"[PLAYER] Stratz API failed: {error}, falling back to OpenDota")
        except httpx.TimeoutException:
            print(f"[PLAYER] Stratz API timeout, falling back to OpenDota")
        except Exception as e:
            print(f"[PLAYER] Stratz API error: {e}, falling back to OpenDota")

    # Если включён режим stratz_only, не используем OpenDota
    if stratz_only:
        print(f"[PLAYER] Stratz-only mode enabled, skipping OpenDota")
        return {"error": "⚠️ Оба API (Stratz и OpenDota) недоступны из вашей сети. Попробуйте: 1) Включить VPN 2) Проверить интернет-соединение 3) Использовать другой провайдер/DNS"}

    # Fallback to OpenDota API
    print(f"[PLAYER] Using OpenDota API fallback...")
    # Увеличиваем таймаут для OpenDota API (они часто медленные)
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=6.0, pool=6.0)) as client:
        try:
            if not hero_map:
                print(f"[PLAYER] Loading hero map...")
                heroes_response = await fetch_json(
                    client,
                    f"{OPEN_DOTA_API}/constants/heroes",
                    {},
                    label="heroes_constants",
                    max_retries=0,
                )
                if isinstance(heroes_response, dict):
                    hero_map = {
                        to_int(hero_id, 0): str(hero_data.get("name") or "").replace("npc_dota_hero_", "")
                        for hero_id, hero_data in heroes_response.items()
                        if isinstance(hero_data, dict) and to_int(hero_id, 0) > 0
                    }
                if not hero_map:
                    hero_map = load_local_hero_map()
                print(f"[PLAYER] Loaded {len(hero_map)} heroes")

            if not item_map:
                print(f"[PLAYER] Loading item map...")
                items_response = await fetch_json(
                    client,
                    f"{OPEN_DOTA_API}/constants/items",
                    {},
                    label="items_constants",
                    max_retries=0,
                )
                if isinstance(items_response, dict):
                    parsed_items = {}
                    for item_name, item_data in items_response.items():
                        item_id = to_int(item_data.get("id"), 0)
                        if item_id <= 0:
                            continue

                        parsed_items[item_id] = {
                            "name": item_data.get("dname") or item_name.replace("_", " ").title(),
                            "image": item_image_url(item_data.get("img")),
                            "slug": str(item_name or "").strip(),
                        }
                    item_map = parsed_items
                if not item_map:
                    item_map = load_local_item_map()
                print(f"[PLAYER] Loaded {len(item_map)} items")

            print(f"[PLAYER] Fetching player data from OpenDota...")

            print(f"[PLAYER] Fetching player profile...")
            print(f"[PLAYER] Fetching matches data...")
            user_task = fetch_json(
                client,
                f"{OPEN_DOTA_API}/players/{player_id}",
                {},
                label="player_data",
                max_retries=0,
                request_timeout=httpx.Timeout(8.0, connect=4.0),
            )
            matches_task = fetch_json(
                client,
                f"{OPEN_DOTA_API}/players/{player_id}/matches?limit={RECENT_MATCHES_LIMIT}&significant=0",
                [],
                label="matches",
                max_retries=0,
                request_timeout=httpx.Timeout(12.0, connect=4.0),
            )
            user_data, matches_raw = await asyncio.gather(user_task, matches_task)

            if not isinstance(user_data, dict):
                user_data = {}
            if not isinstance(user_data.get("profile"), dict):
                print(f"[PLAYER] Profile endpoint unavailable, using lightweight fallback profile")
                user_data["profile"] = {
                    "personaname": f"Player {player_id}",
                    "avatarfull": "",
                }
                user_data["rank_tier"] = to_int(user_data.get("rank_tier"), 0)
                user_data["leaderboard_rank"] = user_data.get("leaderboard_rank")

            if not isinstance(matches_raw, list):
                matches_raw = []
            if not matches_raw:
                return json_payload_response({"error": "Не удалось получить матчи игрока. OpenDota временно недоступен."})
            
            print(f"[PLAYER] Fetching win/loss data...")
            wl_all_modes_task = fetch_json(client, f"{OPEN_DOTA_API}/players/{player_id}/wl?significant=0", {}, label="wl_all_modes", max_retries=0, request_timeout=httpx.Timeout(8.0, connect=4.0))
            wl_default_task = fetch_json(client, f"{OPEN_DOTA_API}/players/{player_id}/wl", {}, label="wl_default", max_retries=0, request_timeout=httpx.Timeout(8.0, connect=4.0))
            turbo_wl_task = fetch_json(client, f"{OPEN_DOTA_API}/players/{player_id}/wl?game_mode=23&significant=0", {}, label="turbo_wl", max_retries=0, request_timeout=httpx.Timeout(8.0, connect=4.0))
            
            print(f"[PLAYER] Fetching heroes, peers, and totals data...")
            heroes_task = fetch_json(client, f"{OPEN_DOTA_API}/players/{player_id}/heroes?significant=0", [], label="heroes_totals", max_retries=0, request_timeout=httpx.Timeout(10.0, connect=4.0))
            peers_task = fetch_json(client, f"{OPEN_DOTA_API}/players/{player_id}/peers", [], label="peers", max_retries=0, request_timeout=httpx.Timeout(8.0, connect=4.0))
            totals_task = fetch_json(client, f"{OPEN_DOTA_API}/players/{player_id}/totals", [], label="totals", max_retries=0, request_timeout=httpx.Timeout(8.0, connect=4.0))
            totals_all_task = fetch_json(client, f"{OPEN_DOTA_API}/players/{player_id}/totals?significant=0", [], label="totals_all_modes", max_retries=0, request_timeout=httpx.Timeout(8.0, connect=4.0))
            (
                wl_all_modes_data,
                wl_default_data,
                turbo_wl_data,
                heroes_totals_raw,
                peers_raw,
                totals_raw,
                totals_all_modes_raw,
            ) = await asyncio.gather(
                wl_all_modes_task,
                wl_default_task,
                turbo_wl_task,
                heroes_task,
                peers_task,
                totals_task,
                totals_all_task,
            )
            recent_matches_stats_raw = []

            recent_matches_source = matches_raw[:RECENT_TABLE_LIMIT]
            recent_match_details = {}
            # OpenDota match detail endpoints are unstable and can freeze the whole
            # dashboard for tens of seconds. For responsiveness we build recent match
            # cards from the lightweight player matches feed and only use detail
            # payloads when they are already available from another source.

            window_25_matches = matches_raw[:25]
            window_100_matches = matches_raw[:100]

            window_stats_25 = compute_window_stats(window_25_matches)
            window_stats_100 = compute_window_stats(window_100_matches)
            window_stats_25["winrate_delta"] = compute_winrate_delta(matches_raw, 25)
            window_stats_100["winrate_delta"] = compute_winrate_delta(matches_raw, 100)

            windows = {
                "25": window_stats_25,
                "100": window_stats_100,
            }

            default_window = window_stats_25 if window_stats_25["matches"] > 0 else window_stats_100

            turbo_wins = to_int(turbo_wl_data.get("win"), -1)
            turbo_losses = to_int(turbo_wl_data.get("lose"), -1)

            if turbo_wins < 0 or turbo_losses < 0:
                turbo_matches_sample = [match for match in matches_raw if to_int(match.get("game_mode"), -1) == 23]
                turbo_wins = sum(1 for match in turbo_matches_sample if is_match_win(match))
                turbo_losses = len(turbo_matches_sample) - turbo_wins

            turbo_total = turbo_wins + turbo_losses
            turbo_wr = round((turbo_wins / turbo_total) * 100, 2) if turbo_total > 0 else 0

            all_modes_wins = to_int(wl_all_modes_data.get("win"), -1)
            all_modes_losses = to_int(wl_all_modes_data.get("lose"), -1)
            all_modes_total = all_modes_wins + all_modes_losses
            if all_modes_wins >= 0 and all_modes_losses >= 0 and all_modes_total > 0:
                wins_all = all_modes_wins
                losses_all = all_modes_losses
            elif to_int(wl_default_data.get("win"), 0) + to_int(wl_default_data.get("lose"), 0) > 0:
                wins_all = to_int(wl_default_data.get("win"), 0)
                losses_all = to_int(wl_default_data.get("lose"), 0)
            else:
                wins_all = default_window["wins"]
                losses_all = default_window["losses"]

            total_matches = wins_all + losses_all

            if total_matches == 0 and default_window["matches"] > 0:
                wins_all = default_window["wins"]
                losses_all = default_window["losses"]
                total_matches = default_window["matches"]

            total_wr = round((wins_all / total_matches) * 100, 2) if total_matches > 0 else 0
            first_match_date = await resolve_first_match_date(client, player_id, total_matches, matches_raw)

            global_avg_gpm = totals_average(totals_all_modes_raw, "gold_per_min") or totals_average(totals_raw, "gold_per_min")
            global_avg_xpm = totals_average(totals_all_modes_raw, "xp_per_min") or totals_average(totals_raw, "xp_per_min")
            recent_avg_gpm = average_positive(recent_matches_stats_raw, "gold_per_min")
            recent_avg_xpm = average_positive(recent_matches_stats_raw, "xp_per_min")
            matches_avg_gpm = average_positive(matches_raw, "gold_per_min")
            matches_avg_xpm = average_positive(matches_raw, "xp_per_min")

            gpm_fallback = next((value for value in [global_avg_gpm, recent_avg_gpm, matches_avg_gpm] if value > 0), 0)
            xpm_fallback = next((value for value in [global_avg_xpm, recent_avg_xpm, matches_avg_xpm] if value > 0), 0)

            for window_key in ("25", "100"):
                if windows[window_key]["avg_gpm"] <= 0 and gpm_fallback > 0:
                    windows[window_key]["avg_gpm"] = gpm_fallback
                if windows[window_key]["avg_xpm"] <= 0 and xpm_fallback > 0:
                    windows[window_key]["avg_xpm"] = xpm_fallback

            recent_wr = default_window["recent_wr"]
            avg_kda = default_window["avg_kda"]
            avg_kills = default_window["avg_kills"]
            avg_deaths = default_window["avg_deaths"]
            avg_assists = default_window["avg_assists"]
            avg_gpm = windows["25"]["avg_gpm"] if windows["25"]["matches"] > 0 else windows["100"]["avg_gpm"]
            avg_xpm = windows["25"]["avg_xpm"] if windows["25"]["matches"] > 0 else windows["100"]["avg_xpm"]
            top_heroes = default_window["top_heroes"]
            win_trend = default_window["win_trend"]

            recent_matches_prepared = []
            for match in recent_matches_source:
                match_id = to_int(match.get("match_id"), 0)
                match_detail = recent_match_details.get(match_id, {})
                player_detail = pick_player_from_match_detail(match_detail, player_id, match)

                hero_id = player_detail.get("hero_id", match.get("hero_id"))
                hero_name = hero_map.get(hero_id, "unknown")
                kills = to_int(player_detail.get("kills", match.get("kills")), 0)
                deaths = to_int(player_detail.get("deaths", match.get("deaths")), 0)
                assists = to_int(player_detail.get("assists", match.get("assists")), 0)
                start_time = to_int(match_detail.get("start_time", match.get("start_time")), 0)
                mode_id = to_int(match_detail.get("game_mode", match.get("game_mode")), 0)
                player_slot = to_int(player_detail.get("player_slot", match.get("player_slot")), 0)
                radiant_win = bool(match_detail.get("radiant_win", match.get("radiant_win", False)))
                is_win = (player_slot < 128 and radiant_win) or (player_slot >= 128 and not radiant_win)

                items = []
                for item_slot in range(6):
                    item_payload = build_item_payload(player_detail.get(f"item_{item_slot}", match.get(f"item_{item_slot}")))
                    if item_payload:
                        items.append(item_payload)

                neutral_item = build_item_payload(player_detail.get("item_neutral", match.get("item_neutral")), is_neutral=True)
                if neutral_item:
                    items.append(neutral_item)

                recent_matches_prepared.append(
                    {
                        "match_id": match_id or match.get("match_id"),
                        "player_slot": player_slot,
                        "radiant_win": radiant_win,
                        "is_win": is_win,
                        "hero_id": hero_id,
                        "hero_name": hero_name,
                        "hero_image": hero_image_url(hero_name),
                        "kills": kills,
                        "deaths": deaths,
                        "assists": assists,
                        "kda_impact": kills + assists - deaths,
                        "level": to_int(player_detail.get("level", match.get("level")), 0),
                        "game_mode": mode_id,
                        "game_mode_label": format_game_mode(mode_id),
                        "duration": to_int(match_detail.get("duration", match.get("duration")), 0),
                        "duration_label": format_duration(match_detail.get("duration", match.get("duration"))),
                        "match_date": format_match_date(start_time),
                        "time_ago": format_time_ago(start_time),
                        "start_time": start_time,
                        "items": items,
                    }
                )

            rank_tier = to_int(user_data.get("rank_tier"), 0)
            leaderboard_rank_raw = user_data.get("leaderboard_rank")
            leaderboard_rank = to_int(leaderboard_rank_raw, 0) if leaderboard_rank_raw is not None else None
            if leaderboard_rank == 0:
                leaderboard_rank = None

            most_played_heroes = build_most_played_heroes(heroes_totals_raw, total_matches)
            if not most_played_heroes:
                most_played_heroes = [
                    {
                        "hero_name": hero["hero_name"],
                        "games": hero["games"],
                        "wins": round(hero["games"] * (hero["winrate"] / 100)),
                        "winrate": round(hero["winrate"], 1),
                        "pick_rate": round((hero["games"] / default_window["matches"]) * 100, 1) if default_window["matches"] > 0 else 0,
                    }
                    for hero in sorted(default_window["top_heroes"], key=lambda item: item["games"], reverse=True)[:MOST_PLAYED_LIMIT]
                ]

            top_allies = build_top_allies(peers_raw)
            activity_matches = await fetch_year_activity_matches(client, player_id, days=ACTIVITY_DAYS)
            activity = build_activity_heatmap(activity_matches if activity_matches else matches_raw, ACTIVITY_DAYS)
            meta_guides = build_meta_guides(default_window["top_heroes"], most_played_heroes, limit=5)

            print(f"[PLAYER] Successfully prepared data for {user_data['profile'].get('personaname', 'Unknown')}")

            response_payload = {
                "account_id": to_int(player_id, 0),
                "name": user_data["profile"].get("personaname", "Unknown"),
                "avatar": user_data["profile"].get("avatarfull", ""),
                "rank": format_rank(rank_tier, leaderboard_rank),
                "rank_tier": rank_tier,
                "leaderboard_rank": leaderboard_rank,
                "total_matches": total_matches,
                "total_wr": total_wr,
                "wins": wins_all,
                "losses": losses_all,
                "first_match": first_match_date,
                "recent_wr": recent_wr,
                "win_trend": win_trend,
                "avg_kda": avg_kda,
                "avg_kills": avg_kills,
                "avg_deaths": avg_deaths,
                "avg_assists": avg_assists,
                "avg_gpm": avg_gpm,
                "avg_xpm": avg_xpm,
                "turbo_stats": {
                    "matches": turbo_total,
                    "wins": turbo_wins,
                    "losses": turbo_losses,
                    "wr": turbo_wr,
                },
                "top_heroes": top_heroes,
                "most_played_heroes": most_played_heroes,
                "top_allies": top_allies,
                "meta_guides": meta_guides,
                "activity": activity,
                "matches": recent_matches_prepared,
                "windows": windows,
                "radar_data": default_window["radar_data"],
            }
            store_cached_player_payload(player_id, response_payload, stratz_only=stratz_only)
            await db.store_cached_player(player_id, stratz_only, response_payload)
            return json_payload_response(response_payload)
        except Exception as error:
            print(f"[PLAYER] Error: {error}")
            import traceback
            traceback.print_exc()
            return json_payload_response({"error": "Ошибка при загрузке данных игрока"})


if __name__ == "__main__":
    # Hosting platforms assign the port through $PORT and route to 0.0.0.0, so a
    # hard-coded 127.0.0.1 would leave the container unreachable. proxy_headers
    # makes request.base_url report the public https:// origin - Steam OpenID signs
    # that origin into openid.realm/return_to, so without it login breaks once the
    # app sits behind a TLS proxy. Only trust forwarded headers from the proxies
    # named in FORWARDED_ALLOW_IPS.
    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=to_int(os.getenv("PORT"), 8000),
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )
