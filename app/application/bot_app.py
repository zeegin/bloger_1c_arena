from __future__ import annotations

import logging
from typing import List

from aiogram import Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from .container import AppContainer
from .pages import Page, PageButton
from .workflow import BotWorkflow


class TelegramBotApp:
    def __init__(self, container: AppContainer, *, max_message_length: int = 3800):
        self.container = container
        self.max_message_length = max_message_length
        self.workflow = BotWorkflow(
            arena=container.arena_service,
            rating_queries=container.rating_queries,
            players=container.players_service,
            deathmatch=container.deathmatch_service,
            presenter=container.presenter,
            top_limit=container.config.top_n,
            reward_350_url=container.config.reward_350_url,
            reward_700_url=container.config.reward_700_url,
        )
        self._logger = logging.getLogger(__name__)

    @property
    def players(self):
        return self.container.players_service

    def _chunk_text(self, text: str) -> List[str]:
        lines = text.split("\n")
        chunks: list[str] = []
        current = ""
        for line in lines:
            addition = line if not current else "\n" + line
            if len(current) + len(addition) > self.max_message_length:
                if current:
                    chunks.append(current)
                current = line
                while len(current) > self.max_message_length:
                    chunks.append(current[: self.max_message_length])
                    current = current[self.max_message_length :]
            else:
                current += addition
        if current:
            chunks.append(current)
        return chunks

    def _build_markup(self, buttons: list[list[PageButton]]):
        if not buttons:
            return None
        inline_rows = [
            [InlineKeyboardButton(text=btn.text, callback_data=btn.callback_data) for btn in row]
            for row in buttons
        ]
        return InlineKeyboardMarkup(inline_keyboard=inline_rows)

    async def _render_page(self, chat_id: int, bot, page: Page):
        for media in page.media:
            if media.kind == "duel":
                a, b = media.channels
                photo = await self.container.media_service.build_duel_preview(a, b)
                await bot.send_photo(
                    chat_id,
                    photo=BufferedInputFile(photo.getvalue(), filename="duel.jpg"),
                    parse_mode="HTML",
                    disable_notification=True,
                )
        chunks = self._chunk_text(page.text)
        markup = self._build_markup(page.buttons)
        total = len(chunks)
        for idx, chunk in enumerate(chunks):
            await bot.send_message(
                chat_id,
                chunk,
                parse_mode=page.parse_mode,
                disable_web_page_preview=page.disable_preview,
                reply_markup=markup if idx == total - 1 else None,
            )

    async def _safe_answer(self, cq: CallbackQuery):
        try:
            await cq.answer()
        except TelegramBadRequest as exc:
            if "query is too old" in str(exc).lower():
                return
            raise

    async def _ensure_user(self, tg_user):
        return await self.players.upsert_user(tg_user.id, tg_user.username, tg_user.first_name)

    def _format_user(self, tg_user) -> str:
        if not tg_user:
            return "unknown (id=?)"
        username = tg_user.username or tg_user.first_name or "unknown"
        return f"{username} (id={tg_user.id})"

    def _log_action(self, tg_user, action: str) -> None:
        self._logger.info("User %s triggered %s", self._format_user(tg_user), action)

    async def _handle_message(self, message: Message, handler):
        self._log_action(message.from_user, f"message:{message.text or message.content_type}")
        await self._ensure_user(message.from_user)
        page = await handler()
        if page:
            await self._render_page(message.chat.id, message.bot, page)

    async def _handle_query(self, cq: CallbackQuery, handler):
        await self._safe_answer(cq)
        self._log_action(cq.from_user, f"callback:{cq.data or '<empty>'}")
        user_id = await self._ensure_user(cq.from_user)
        page = await handler(user_id, cq)
        if page:
            await self._render_page(cq.message.chat.id, cq.bot, page)

    def build_dispatcher(self) -> Dispatcher:
        dp = Dispatcher()

        @dp.message(F.text == "/start")
        async def start(m: Message):
            await self._handle_message(m, self.workflow.start_page)

        @dp.callback_query(F.data.startswith("menu:"))
        async def menu(cq: CallbackQuery):
            async def handler(user_id, cq):
                data = cq.data or ""
                action = data.split(":", 1)[1] if ":" in data else ""
                if action == "play":
                    return await self.workflow.duel_page(user_id)
                if action == "top":
                    return await self.workflow.top_page(user_id)
                if action == "deathmatch":
                    return await self.workflow.start_deathmatch(user_id)
                return await self.workflow.top_page(user_id)

            await self._handle_query(cq, handler)

        @dp.callback_query(F.data == "top:100")
        async def top100(cq: CallbackQuery):
            await self._handle_query(cq, lambda _user_id, _cq: self.workflow.top100_page())

        @dp.callback_query(F.data == "top:back")
        async def top_back(cq: CallbackQuery):
            await self._handle_query(cq, lambda user_id, _cq: self.workflow.top_page(user_id))

        @dp.callback_query(F.data == "top:favorites")
        async def top_favorites(cq: CallbackQuery):
            await self._handle_query(cq, lambda user_id, _cq: self.workflow.favorites_page(user_id))

        @dp.callback_query(F.data == "top:winrate")
        async def top_winrate(cq: CallbackQuery):
            await self._handle_query(cq, lambda _user_id, _cq: self.workflow.weighted_top_page())

        @dp.callback_query(F.data.startswith("vote:"))
        async def vote(cq: CallbackQuery):
            async def handler(user_id, cq):
                parts = (cq.data or "").split(":")
                if len(parts) != 5:
                    return None
                _, token, a_id, b_id, winner = parts
                return await self.workflow.process_vote(
                    user_id,
                    token=token,
                    a_id=int(a_id),
                    b_id=int(b_id),
                    winner=winner,
                )

            await self._handle_query(cq, handler)

        @dp.callback_query(F.data.startswith("dmvote:"))
        async def deathmatch_vote(cq: CallbackQuery):
            async def handler(user_id, cq):
                parts = (cq.data or "").split(":")
                if len(parts) != 5:
                    return None
                _, token, a_id, b_id, winner = parts
                return await self.workflow.process_deathmatch_vote(
                    user_id,
                    token=token,
                    a_id=int(a_id),
                    b_id=int(b_id),
                    winner=winner,
                )

            await self._handle_query(cq, handler)

        @dp.callback_query(F.data.startswith("deathmatch:"))
        async def deathmatch_actions(cq: CallbackQuery):
            async def handler(user_id, cq):
                action = (cq.data or "").split(":", 1)[1]
                if action == "resume":
                    return await self.workflow.resume_deathmatch(user_id)
                if action == "restart":
                    return await self.workflow.restart_deathmatch(user_id)
                return await self.workflow.start_deathmatch(user_id)

            await self._handle_query(cq, handler)

        return dp
