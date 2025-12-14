from __future__ import annotations

from html import escape
from typing import Sequence

from ...domain.deathmatch import DeathmatchRound
from ...domain.shared.models import Channel
from ..queries.rating import FavoriteChannelInfo, FavoritesSummary, TopEntry, TopListing, WeightedEntry
from ..pages import Page, PageButton, PageMediaRequest


class BotPresenter:
    def __init__(self) -> None:
        pass

    def _main_menu_buttons(self) -> list[list[PageButton]]:
        return [
            [PageButton("✅ Арена", "menu:play")],
            [PageButton("🔥 Deathmatch", "menu:deathmatch")],
            [PageButton("📊 Рейтинг", "menu:top")],
        ]

    def _rating_buttons(self, mode: str) -> list[list[PageButton]]:
        if mode == "top20":
            rows = [
                [PageButton("📈 TOP 100", "top:100")],
                [PageButton("⚖️ Рейтинг побед", "top:winrate")],
                [PageButton("❤️ Любимчики", "top:favorites")],
            ]
        elif mode == "top100":
            rows = [[PageButton("⬅️ Топ 20", "top:back")]]
        else:
            rows = [[PageButton("⬅️ Топ 20", "top:back")]]
        rows.append([PageButton("✅ Арена", "menu:play")])
        rows.append([PageButton("🔥 Deathmatch", "menu:deathmatch")])
        return rows

    def _link(self, url: str, title: str) -> str:
        return f'<a href="{escape(url, quote=True)}">{escape(title)}</a>'

    def _format_description(self, description: str | None) -> str:
        if not description:
            return ""
        stripped = description.strip()
        if not stripped:
            return ""
        return escape(stripped)

    def _format_channel_block(self, label: str, channel: Channel) -> str:
        block = [f"<b>{label}:</b> {self._link(channel.tg_url, channel.title)}"]
        desc = self._format_description(channel.description)
        if desc:
            block.append(desc)
        return "\n".join(block)

    def _format_top_entries(self, entries: Sequence[TopEntry]) -> str:
        lines = []
        for idx, entry in enumerate(entries, start=1):
            rating = int(round(entry.rating))
            lines.append(
                f"{idx}. {self._link(entry.tg_url, entry.title)} — <b>{rating}</b> "
                f"(игр: {entry.games}, побед: {entry.wins})"
            )
        return "\n".join(lines)

    def _format_winrate_entries(self, entries: Sequence[WeightedEntry]) -> str:
        lines = []
        for idx, entry in enumerate(entries, start=1):
            lines.append(
                f"{idx}. {self._link(entry.tg_url, entry.title)} — <b>{entry.rate_percent:.1f}%</b> "
                f"(побед: {entry.wins}, игр: {entry.games})"
            )
        return "\n".join(lines)

    def _format_favorites(self, favorites: Sequence[FavoriteChannelInfo]) -> str:
        lines = []
        for idx, fav in enumerate(favorites, start=1):
            lines.append(f"{idx}. {self._link(fav.tg_url, fav.title)} — <b>{fav.fans}</b>")
        return "\n".join(lines)

    def start_page(self) -> Page:
        return Page(
            "Привет! Я собираю рейтинг каналов по системе Elo.\nВыбирай, какой из двух каналов лучше.",
            buttons=self._main_menu_buttons(),
        )

    def rating_locked_page(self, min_games: int, current_games: int) -> Page:
        remaining = max(0, min_games - current_games)
        text = (
            "📊 Рейтинг откроется после классических игр на арене.\n"
            f"Нужно: <b>{min_games}</b>, сыграно: <b>{current_games}</b>.\n"
            f"Продолжай голосовать! Осталось: <b>{remaining}</b>."
        )
        return Page(text, buttons=self._main_menu_buttons())

    def duel_unavailable(self) -> Page:
        return Page("Нужно минимум 2 канала в базе.", buttons=self._main_menu_buttons())

    def duel_page(self, duel) -> Page:
        a, b = duel.channel_a, duel.channel_b
        text_lines = [
            f"Выбери канал из рейтинга <b>{escape(duel.rating_band)}</b>:",
            "",
            self._format_channel_block("A", a),
            "",
            self._format_channel_block("B", b),
        ]
        text = "\n".join(text_lines)
        buttons = [
            [
                PageButton("👍 Выбрать A", f"vote:{duel.token}:{a.id}:{b.id}:A"),
                PageButton("👍 Выбрать B", f"vote:{duel.token}:{a.id}:{b.id}:B"),
            ],
            [PageButton("🤝 Ничья", f"vote:{duel.token}:{a.id}:{b.id}:D")],
            [PageButton("📊 Рейтинг", "menu:top")],
        ]
        media = [PageMediaRequest(kind="duel", channels=(a, b))]
        return Page(text, buttons=buttons, media=media)

    def top_empty(self) -> Page:
        return Page("Пока нет каналов в базе.", buttons=self._main_menu_buttons())

    def top_page(self, listing: TopListing, player_stats: dict | None = None) -> Page:
        parts = [
            "📊 <b>Топ каналов:</b>",
            "",
            self._format_top_entries(listing.entries),
            "",
            f"🕹️ Сыграно игр: <b>{listing.stats.games}</b>",
            f"👥 Игроков: <b>{listing.stats.players}</b>",
        ]
        if player_stats is not None:
            parts.extend(
                [
                    "",
                    "👤 <b>Твоя статистика:</b>",
                    f"- Классических игр: <b>{player_stats['classic_games']}</b>",
                    f"- Ничьих: <b>{player_stats['draws']}</b>",
                ]
            )
        text = "\n".join(parts)
        return Page(text, buttons=self._rating_buttons("top20"))

    def top100_page(self, entries: Sequence[TopEntry], *, show_all: bool) -> Page:
        heading = "📈 <b>Все каналы:</b>" if show_all else "📈 <b>TOP 100:</b>"
        text = "\n".join(
            [
                heading,
                "",
                self._format_top_entries(entries),
            ]
        )
        return Page(text, buttons=self._rating_buttons("top100"))

    def winrate_top_page(self, entries: Sequence[WeightedEntry]) -> Page:
        text = "\n".join(
            [
                "⚖️ <b>Рейтинг побед:</b>",
                "Основан только на отношении побед к играм.",
                "",
                self._format_winrate_entries(entries),
            ]
        )
        return Page(text, buttons=self._rating_buttons("winrate"))

    def winrate_top_empty(self) -> Page:
        return Page("Пока нет каналов в базе.", buttons=self._rating_buttons("winrate"))

    def favorites_empty(self) -> Page:
        return Page("Пока никто не выбрал любимчика.", buttons=self._rating_buttons("favorites"))

    def favorites_page(
        self,
        summary: FavoritesSummary,
        user_favorite: Channel | None,
        *,
        player_dm_games: int | None = None,
    ) -> Page:
        parts = [
            "❤️ <b>Рейтинг Deathmatch:</b>",
            "",
            self._format_favorites(summary.favorites),
            "",
            f"🕹️ Deathmatch игр: <b>{summary.stats.games}</b>",
            f"👥 Deathmatch игроков: <b>{summary.stats.players}</b>",
        ]
        if player_dm_games is not None:
            parts.append(f"🎮 Ты сыграл в deathmatch: <b>{player_dm_games}</b>")
        if user_favorite:
            parts.append(f"❤️ Твой любимчик: {self._link(user_favorite.tg_url, user_favorite.title)}")
        text = "\n".join(parts)
        return Page(text, buttons=self._rating_buttons("favorites"))

    def deathmatch_need_classic_games(self, min_games: int, remaining: int) -> Page:
        played = max(0, min_games - remaining)
        text = (
            "🔥 Deathmatch откроется после классических игр на арене.\n"
            f"Нужно: <b>{min_games}</b>, сыграно: <b>{played}</b>.\n"
            f"Продолжай голосовать! Осталось: <b>{remaining}</b>."
        )
        return Page(text, buttons=self._main_menu_buttons())

    def deathmatch_not_enough_channels(self) -> Page:
        return Page("Недостаточно каналов в топе, чтобы начать deathmatch.", buttons=self._main_menu_buttons())

    def deathmatch_error(self) -> Page:
        return Page("Не удалось стартовать deathmatch. Попробуй позже.", buttons=self._main_menu_buttons())

    def deathmatch_round_page(self, round_info: DeathmatchRound) -> Page:
        a = round_info.current
        b = round_info.opponent
        first_label = "A" if round_info.initial else "👑 Чемпион"
        second_label = "B" if round_info.initial else "🥊 Претендент"
        intro = (
            "🔥 Deathmatch стартует! Это игра на выбывание: участвует только топ из классики, "
            "а турнир заканчивается, когда ты пройдёшь все каналы."
            if round_info.initial
            else "🔥 Deathmatch продолжается! Чемпион ждёт нового соперника."
        )
        text = "\n".join(
            [
                intro,
                "",
                f"Раунд <b>{round_info.number}</b> из <b>{round_info.total}</b>.",
                "",
                self._format_channel_block(first_label, a),
                "",
                self._format_channel_block(second_label, b),
            ]
        )
        buttons = [
            [
                PageButton("👑 Выбрать A", f"dmvote:{round_info.token}:{a.id}:{b.id}:A"),
                PageButton("🥊 Выбрать B", f"dmvote:{round_info.token}:{a.id}:{b.id}:B"),
            ],
            [PageButton("📊 Рейтинг", "menu:top")],
        ]
        media = [PageMediaRequest(kind="duel", channels=(a, b))]
        return Page(text, buttons=buttons, media=media)

    def reward_page(self, games: int, url: str) -> Page:
        text = "\n".join(
            [
                f"🎁 Спасибо за {games} игр в арене!",
                f"Вот секретный подарок: {escape(url)}",
            ]
        )
        return Page(text, buttons=self._main_menu_buttons(), disable_preview=False)

    def deathmatch_unlocked_page(self, games: int, min_games: int) -> Page:
        text = (
            f"🎉 Спасибо за {games} игр в классике!\n\n"
            f"Теперь тебе открыт режим <b>🔥 Deathmatch</b>, доступный после {min_games} матчей. "
            "Нажми кнопку в меню и попробуй себя в битве чемпионов."
        )
        return Page(text, buttons=self._main_menu_buttons())

    def deathmatch_resume_prompt(self) -> Page:
        text = (
            "🔥 У тебя есть незавершённый deathmatch.\n"
            "Продолжить текущий турнир или начать заново по актуальному топу классики?"
        )
        buttons = [
            [
                PageButton("▶️ Продолжить", "deathmatch:resume"),
                PageButton("🔄 Начать заново", "deathmatch:restart"),
            ],
        ]
        buttons.extend(self._main_menu_buttons())
        return Page(text, buttons=buttons)

    def duplicate_classic_vote(self) -> Page:
        return Page("Голос уже учтён. Запроси новый дуэль.", buttons=self._main_menu_buttons())

    def duplicate_deathmatch_vote(self) -> Page:
        return Page("Голос уже учтён. Ждём следующий вызов!", buttons=self._main_menu_buttons())

    def deathmatch_state_missing(self) -> Page:
        return Page(
            "Deathmatch ещё не запущен. Нажми «🔥 Deathmatch» в меню.",
            buttons=self._main_menu_buttons(),
        )

    def deathmatch_finished(self, champion: Channel) -> Page:
        title = escape(champion.title)
        url = escape(champion.tg_url)
        text = f"🏆 Deathmatch завершён!\n<b>Победитель:</b> <a href=\"{url}\">{title}</a>\nОн сохранён как твой любимчик."
        return Page(text, buttons=self._main_menu_buttons())

    def deathmatch_round_stale(self) -> Page:
        return Page("Раунд устарел. Нажми «🔥 Deathmatch», чтобы начать заново.", buttons=self._main_menu_buttons())
