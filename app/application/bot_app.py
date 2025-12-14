from __future__ import annotations

import logging
from typing import List

from aiogram import Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from .container import AppContainer
from .pages import Page, PageButton
from .workflow import BotWorkflow
from ..infrastructure.metrics import metrics

DUEL_CAPTION_LIMIT = 1024


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
            min_rating_games=container.config.min_rating_games,
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

    def _pop_caption_chunk(self, chunks: List[str]) -> str | None:
        if not chunks:
            return None
        text = chunks.pop(0)
        if len(text) <= DUEL_CAPTION_LIMIT:
            return text
        caption = text[:DUEL_CAPTION_LIMIT]
        remainder = text[DUEL_CAPTION_LIMIT:].lstrip("\n")
        if remainder:
            chunks.insert(0, remainder)
        return caption

    def _build_markup(self, buttons: list[list[PageButton]]):
        if not buttons:
            return None
        inline_rows = [
            [InlineKeyboardButton(text=btn.text, callback_data=btn.callback_data) for btn in row]
            for row in buttons
        ]
        return InlineKeyboardMarkup(inline_keyboard=inline_rows)

    async def _render_page(self, chat_id: int, bot, page: Page, *, extra_metrics: dict | None = None):
        chunks = self._chunk_text(page.text)
        markup = self._build_markup(page.buttons)
        for media in page.media:
            if media.kind != "duel":
                continue
            a, b = media.channels
            photo, cache_state = await self.container.media_service.build_duel_preview(a, b)
            if extra_metrics is not None and cache_state:
                extra_metrics["media_cache"] = cache_state
            caption = self._pop_caption_chunk(chunks)
            is_last = not chunks
            await bot.send_photo(
                chat_id,
                photo=BufferedInputFile(photo.getvalue(), filename="duel.jpg"),
                caption=caption,
                parse_mode=page.parse_mode,
                disable_notification=True,
                reply_markup=markup if is_last else None,
            )
        total = len(chunks)
        for idx, chunk in enumerate(chunks):
            is_last = idx == total - 1
            await bot.send_message(
                chat_id,
                chunk,
                parse_mode=page.parse_mode,
                disable_web_page_preview=page.disable_preview,
                reply_markup=markup if is_last else None,
            )

    async def _safe_answer(self, cq: CallbackQuery):
        try:
            await cq.answer()
        except TelegramBadRequest as exc:
            if "query is too old" in str(exc).lower():
                return
            raise

    async def _ensure_user(self, tg_user, state: FSMContext | None):
        if not tg_user:
            return None
        if state is not None:
            data = await state.get_data()
            cached_id = data.get("user_id")
            cached_username = data.get("username")
            cached_first_name = data.get("first_name")
            if (
                cached_id
                and cached_username == tg_user.username
                and cached_first_name == tg_user.first_name
            ):
                return cached_id
        ensured = await self.players.upsert_user(tg_user.id, tg_user.username, tg_user.first_name)
        if state is not None and ensured is not None:
            await state.update_data(
                user_id=ensured,
                username=tg_user.username,
                first_name=tg_user.first_name,
            )
        return ensured

    def _format_user(self, tg_user) -> str:
        if not tg_user:
            return "unknown (id=?)"
        username = tg_user.username or tg_user.first_name or "unknown"
        return f"{username} (id={tg_user.id})"

    def _log_action(self, tg_user, action: str) -> None:
        self._logger.info("User %s triggered %s", self._format_user(tg_user), action)

    async def _handle_message(self, message: Message, handler, state: FSMContext):
        action_name = f"message:{message.text or message.content_type}"
        self._log_action(message.from_user, action_name)
        user_id = message.from_user.id if message.from_user else None
        extra = {"user_id": user_id} if user_id is not None else None
        async with metrics.span_async(action_name, source="telegram", extra=extra):
            await self._ensure_user(message.from_user, state)
            page = await handler()
            if page:
                await self._render_page(message.chat.id, message.bot, page)

    async def _handle_query(self, cq: CallbackQuery, handler, state: FSMContext):
        await self._safe_answer(cq)
        action_name = f"callback:{cq.data or '<empty>'}"
        self._log_action(cq.from_user, action_name)
        user_id = cq.from_user.id if cq.from_user else None
        extra = {"user_id": user_id} if user_id is not None else None
        extra_data = dict(extra or {})
        async with metrics.span_async(action_name, source="telegram", extra=extra_data):
            ensured_id = await self._ensure_user(cq.from_user, state)
            page = await handler(ensured_id, cq)
            if page:
                await self._render_page(cq.message.chat.id, cq.bot, page, extra_metrics=extra_data)

    def build_dispatcher(self) -> Dispatcher:
        dp = Dispatcher(storage=MemoryStorage())

        @dp.message(F.text == "/start")
        async def start(m: Message, state: FSMContext):
            await self._handle_message(m, self.workflow.start_page, state)

        @dp.callback_query(F.data.startswith("menu:"))
        async def menu(cq: CallbackQuery, state: FSMContext):
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

            await self._handle_query(cq, handler, state)

        @dp.callback_query(F.data == "top:100")
        async def top100(cq: CallbackQuery, state: FSMContext):
            await self._handle_query(cq, lambda user_id, _cq: self.workflow.top100_page(user_id), state)

        @dp.callback_query(F.data == "top:back")
        async def top_back(cq: CallbackQuery, state: FSMContext):
            await self._handle_query(cq, lambda user_id, _cq: self.workflow.top_page(user_id), state)

        @dp.callback_query(F.data == "top:favorites")
        async def top_favorites(cq: CallbackQuery, state: FSMContext):
            await self._handle_query(cq, lambda user_id, _cq: self.workflow.favorites_page(user_id), state)

        @dp.callback_query(F.data == "top:winrate")
        async def top_winrate(cq: CallbackQuery, state: FSMContext):
            await self._handle_query(cq, lambda user_id, _cq: self.workflow.winrate_page(user_id), state)

        @dp.callback_query(F.data.startswith("vote:"))
        async def vote(cq: CallbackQuery, state: FSMContext):
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

            await self._handle_query(cq, handler, state)

        @dp.callback_query(F.data.startswith("dmvote:"))
        async def deathmatch_vote(cq: CallbackQuery, state: FSMContext):
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

            await self._handle_query(cq, handler, state)

        @dp.callback_query(F.data.startswith("deathmatch:"))
        async def deathmatch_actions(cq: CallbackQuery, state: FSMContext):
            async def handler(user_id, cq):
                action = (cq.data or "").split(":", 1)[1]
                if action == "resume":
                    return await self.workflow.resume_deathmatch(user_id)
                if action == "restart":
                    return await self.workflow.restart_deathmatch(user_id)
                return await self.workflow.start_deathmatch(user_id)

            await self._handle_query(cq, handler, state)

        return dp
