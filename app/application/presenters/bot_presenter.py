from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Sequence

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ...domain.deathmatch import DeathmatchRound
from ...domain.shared.models import Channel
from ..queries.rating import FavoritesSummary, TopEntry, TopListing, WeightedEntry
from ..pages import Page, PageButton, PageMediaRequest


class BotPresenter:
    def __init__(self, templates_dir: Path | None = None):
        base_dir = templates_dir or (Path(__file__).resolve().parent / "templates")
        self._env = Environment(
            loader=FileSystemLoader(str(base_dir)),
            autoescape=select_autoescape(enabled_extensions=("j2",), default_for_string=True, default=True),
            trim_blocks=True,
            lstrip_blocks=True,
        )

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

    def _render(self, template: str, **context) -> str:
        return self._env.get_template(template).render(**context).strip()

    def start_page(self) -> Page:
        return Page(
            "Привет! Я собираю рейтинг каналов по системе Elo.\nВыбирай, какой из двух каналов лучше.",
            buttons=self._main_menu_buttons(),
        )

    def duel_unavailable(self) -> Page:
        return Page("Нужно минимум 2 канала в базе.", buttons=self._main_menu_buttons())

    def duel_page(self, duel) -> Page:
        a, b = duel.channel_a, duel.channel_b
        text = self._render(
            "duel_page.j2",
            rating_band=duel.rating_band,
            channel_a=a,
            channel_b=b,
        )
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
        text = self._render(
            "top_page.j2",
            entries=listing.entries,
            stats=listing.stats,
            player_stats=player_stats,
        )
        return Page(text, buttons=self._rating_buttons("top20"))

    def top100_page(self, entries: Sequence[TopEntry], *, show_all: bool) -> Page:
        text = self._render("ordered_top_page.j2", entries=entries, show_all=show_all)
        return Page(text, buttons=self._rating_buttons("top100"))

    def weighted_top_page(self, entries: Sequence[WeightedEntry]) -> Page:
        text = self._render("weighted_top_page.j2", entries=entries)
        return Page(text, buttons=self._rating_buttons("weighted"))

    def weighted_top_empty(self) -> Page:
        return Page("Пока нет каналов в базе.", buttons=self._main_menu_buttons())

    def favorites_empty(self) -> Page:
        return Page("Пока никто не выбрал любимчика.", buttons=self._rating_buttons("favorites"))

    def favorites_page(
        self,
        summary: FavoritesSummary,
        user_favorite: Channel | None,
        *,
        player_dm_games: int | None = None,
    ) -> Page:
        text = self._render(
            "favorites_page.j2",
            favorites=summary.favorites,
            stats=summary.stats,
            user_favorite=user_favorite,
            player_dm_games=player_dm_games,
        )
        return Page(text, buttons=self._rating_buttons("favorites"))

    def deathmatch_need_classic_games(self, min_games: int, remaining: int) -> Page:
        text = (
            f"🔥 Deathmatch доступен после {min_games} классических игр. "
            f"Продолжай голосовать в арене! Осталось сыграть: <b>{remaining}</b>."
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
        text = self._render(
            "deathmatch_round.j2",
            initial=round_info.initial,
            first_label=first_label,
            second_label=second_label,
            current=a,
            opponent=b,
            round_number=round_info.number,
            round_total=round_info.total,
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
        text = self._render("reward_page.j2", games=games, url=url)
        return Page(text, buttons=self._main_menu_buttons(), disable_preview=False)

    def deathmatch_unlocked_page(self, games: int, min_games: int) -> Page:
        text = self._render(
            "deathmatch_unlock.j2",
            games=games,
            min_games=min_games,
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
