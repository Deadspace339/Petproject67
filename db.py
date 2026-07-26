"""Хранилище: аккаунты, история поисков, диалоги с AI Coach и кеш профилей.

На Render используется PostgreSQL (DATABASE_URL), локально - файл SQLite, чтобы
не поднимать Postgres на машине разработчика.

Все обращения к базе не должны ронять приложение: дашборд обязан работать и с
недоступной базой, ровно как он переживает отказ STRATZ или OpenDota. Поэтому
публичные функции ниже ловят исключения, пишут их в лог и возвращают безопасное
значение вместо того, чтобы пробрасывать ошибку в обработчик запроса.
"""

import datetime
import os
from typing import Any, Dict, Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SQLITE_URL = f"sqlite+aiosqlite:///{os.path.join(BASE_DIR, 'app.db')}"


def _normalize_database_url(raw_url: str) -> str:
    """Приводит DATABASE_URL к виду, который понимает async-драйвер.

    Render выдаёт строку вида postgres://... - это синхронный диалект, на нём
    create_async_engine падает. Подменяем схему на postgresql+asyncpg.
    """
    url = (raw_url or "").strip()
    if not url:
        return DEFAULT_SQLITE_URL

    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    elif url.startswith("sqlite:///"):
        url = "sqlite+aiosqlite:///" + url[len("sqlite:///"):]

    # asyncpg сам согласует TLS и не понимает libpq-параметр sslmode в строке.
    if "+asyncpg" in url and "sslmode=" in url:
        base, _, query = url.partition("?")
        kept = [p for p in query.split("&") if p and not p.startswith("sslmode=")]
        url = base + ("?" + "&".join(kept) if kept else "")

    return url


# Разрешается не на импорте, а в init_db(): main.py подгружает .env уже после
# импорта модулей, и прочитанный слишком рано DATABASE_URL всегда был бы пустым.
DATABASE_URL = ""
IS_SQLITE = True


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class User(Base):
    """Игрок, вошедший через Steam."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    steam_id64: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    account_id: Mapped[int] = mapped_column(BigInteger, index=True)
    persona_name: Mapped[str] = mapped_column(String(255), default="")
    avatar: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_login_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    login_count: Mapped[int] = mapped_column(Integer, default=0)

    def as_session_payload(self) -> Dict[str, Any]:
        return {
            "steam_id64": self.steam_id64,
            "account_id": self.account_id,
            "persona_name": self.persona_name or f"Steam {self.steam_id64}",
            "avatar": self.avatar or "",
        }


class SearchHistory(Base):
    """Что искали: и авторизованные пользователи, и анонимные."""

    __tablename__ = "search_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    query: Mapped[str] = mapped_column(String(255))
    resolved_account_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class CoachMessage(Base):
    """Реплики диалога с AI Coach, чтобы переписка переживала перезагрузку."""

    __tablename__ = "coach_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="")
    prompt_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class PlayerCache(Base):
    """Кеш ответов /api/player. В памяти он терялся при каждом рестарте."""

    __tablename__ = "player_cache"
    __table_args__ = (UniqueConstraint("account_id", "stratz_only", name="uq_player_cache_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(BigInteger, index=True)
    stratz_only: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


_engine = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
_ready = False


def is_ready() -> bool:
    return _ready


def describe_backend() -> str:
    return "postgresql" if not IS_SQLITE else "sqlite"


async def init_db() -> bool:
    """Поднимает подключение и создаёт таблицы. False - работаем без базы."""
    global _engine, _session_factory, _ready, DATABASE_URL, IS_SQLITE

    DATABASE_URL = _normalize_database_url(os.getenv("DATABASE_URL", ""))
    IS_SQLITE = DATABASE_URL.startswith("sqlite")

    try:
        _engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, future=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
        async with _engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        _ready = True
        print(f"[DB] connected ({describe_backend()})")
    except Exception as error:
        _ready = False
        print(f"[DB] unavailable, running without persistence: {type(error).__name__}: {error}")

    return _ready


async def close_db() -> None:
    global _ready
    _ready = False
    if _engine is not None:
        try:
            await _engine.dispose()
        except Exception:
            pass


async def upsert_user(steam_id64: str, account_id: int, persona_name: str, avatar: str) -> Optional[Dict[str, Any]]:
    """Создаёт или обновляет запись игрока после входа через Steam."""
    if not _ready or _session_factory is None:
        return None

    try:
        async with _session_factory() as session:
            existing = await session.scalar(select(User).where(User.steam_id64 == str(steam_id64)))
            now = _utcnow()

            if existing is None:
                existing = User(
                    steam_id64=str(steam_id64),
                    account_id=int(account_id),
                    persona_name=persona_name or "",
                    avatar=avatar or "",
                    created_at=now,
                    last_login_at=now,
                    login_count=1,
                )
                session.add(existing)
            else:
                existing.account_id = int(account_id)
                # Ник и аватар в Steam меняются - подтягиваем свежие, но пустым
                # ответом профиля затирать уже известные значения не хотим.
                if persona_name:
                    existing.persona_name = persona_name
                if avatar:
                    existing.avatar = avatar
                existing.last_login_at = now
                existing.login_count = (existing.login_count or 0) + 1

            await session.commit()
            return existing.as_session_payload()
    except Exception as error:
        print(f"[DB] upsert_user failed: {type(error).__name__}: {error}")
        return None


async def get_user_by_steam_id(steam_id64: str) -> Optional[Dict[str, Any]]:
    if not _ready or _session_factory is None or not steam_id64:
        return None

    try:
        async with _session_factory() as session:
            user = await session.scalar(select(User).where(User.steam_id64 == str(steam_id64)))
            return user.as_session_payload() if user is not None else None
    except Exception as error:
        print(f"[DB] get_user_by_steam_id failed: {type(error).__name__}: {error}")
        return None


async def _resolve_user_id(session: AsyncSession, steam_id64: Optional[str]) -> Optional[int]:
    if not steam_id64:
        return None
    user = await session.scalar(select(User).where(User.steam_id64 == str(steam_id64)))
    return user.id if user is not None else None


async def record_search(query: str, resolved_account_id: Optional[int], source: str, steam_id64: Optional[str]) -> None:
    if not _ready or _session_factory is None:
        return

    try:
        async with _session_factory() as session:
            session.add(
                SearchHistory(
                    user_id=await _resolve_user_id(session, steam_id64),
                    query=str(query or "")[:255],
                    resolved_account_id=int(resolved_account_id) if resolved_account_id else None,
                    source=str(source or "")[:32],
                )
            )
            await session.commit()
    except Exception as error:
        print(f"[DB] record_search failed: {type(error).__name__}: {error}")


async def record_coach_exchange(
    prompt: str,
    answer: str,
    source: str,
    prompt_id: str,
    steam_id64: Optional[str],
) -> None:
    if not _ready or _session_factory is None:
        return

    try:
        async with _session_factory() as session:
            user_id = await _resolve_user_id(session, steam_id64)
            session.add(CoachMessage(user_id=user_id, role="user", content=str(prompt or ""), prompt_id=str(prompt_id or "")[:64]))
            session.add(
                CoachMessage(
                    user_id=user_id,
                    role="assistant",
                    content=str(answer or ""),
                    source=str(source or "")[:32],
                    prompt_id=str(prompt_id or "")[:64],
                )
            )
            await session.commit()
    except Exception as error:
        print(f"[DB] record_coach_exchange failed: {type(error).__name__}: {error}")


async def get_cached_player(account_id: int, stratz_only: bool, ttl_seconds: int) -> Optional[Dict[str, Any]]:
    if not _ready or _session_factory is None:
        return None

    try:
        async with _session_factory() as session:
            row = await session.scalar(
                select(PlayerCache).where(
                    PlayerCache.account_id == int(account_id),
                    PlayerCache.stratz_only == (1 if stratz_only else 0),
                )
            )
            if row is None or not isinstance(row.payload, dict):
                return None

            updated_at = row.updated_at
            if updated_at is None:
                return None
            # SQLite отдаёт naive datetime, Postgres - aware. Приводим к UTC.
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=datetime.UTC)

            age = (_utcnow() - updated_at).total_seconds()
            if age < 0 or age > ttl_seconds:
                return None
            return row.payload
    except Exception as error:
        print(f"[DB] get_cached_player failed: {type(error).__name__}: {error}")
        return None


async def store_cached_player(account_id: int, stratz_only: bool, payload: Dict[str, Any]) -> None:
    if not _ready or _session_factory is None or not isinstance(payload, dict) or payload.get("error"):
        return

    try:
        async with _session_factory() as session:
            row = await session.scalar(
                select(PlayerCache).where(
                    PlayerCache.account_id == int(account_id),
                    PlayerCache.stratz_only == (1 if stratz_only else 0),
                )
            )
            if row is None:
                session.add(
                    PlayerCache(
                        account_id=int(account_id),
                        stratz_only=1 if stratz_only else 0,
                        payload=payload,
                        updated_at=_utcnow(),
                    )
                )
            else:
                row.payload = payload
                row.updated_at = _utcnow()
            await session.commit()
    except Exception as error:
        print(f"[DB] store_cached_player failed: {type(error).__name__}: {error}")


async def get_stats() -> Dict[str, Any]:
    """Сводка для эндпоинта /api/admin/stats."""
    if not _ready or _session_factory is None:
        return {"available": False}

    try:
        async with _session_factory() as session:
            return {
                "available": True,
                "backend": describe_backend(),
                "users": await session.scalar(select(func.count()).select_from(User)) or 0,
                "searches": await session.scalar(select(func.count()).select_from(SearchHistory)) or 0,
                "coach_messages": await session.scalar(select(func.count()).select_from(CoachMessage)) or 0,
                "cached_players": await session.scalar(select(func.count()).select_from(PlayerCache)) or 0,
            }
    except Exception as error:
        print(f"[DB] get_stats failed: {type(error).__name__}: {error}")
        return {"available": False}
