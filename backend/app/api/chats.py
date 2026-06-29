"""Chat lifecycle: create/list/get, upload context docs, submit the idea (runs the
council pipeline in the background), and fetch the final report."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.orchestrator import run_council
from app.api.deps import get_current_user
from app.core.db import get_session
from app.models import Chat, ChatDocument, ChatStatus, CouncilReport, User
from app.schemas.api import (
    ChatCreate,
    ChatDetail,
    ChatOut,
    DocumentOut,
    ReportOut,
    SubmitItem,
)

router = APIRouter(prefix="/api/chats", tags=["chats"])

# Hold references to background pipeline tasks so they aren't garbage-collected.
_pipeline_tasks: set[asyncio.Task] = set()


async def _load_owned_chat(session: AsyncSession, chat_id: str, user: User) -> Chat:
    chat = await session.get(Chat, chat_id)
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status_code=404, detail="chat not found")
    return chat


@router.post("", response_model=ChatOut)
async def create_chat(
    body: ChatCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Chat:
    chat = Chat(user_id=user.id, title=body.title, idea=body.idea)
    session.add(chat)
    await session.commit()
    await session.refresh(chat)
    return chat


@router.get("", response_model=list[ChatOut])
async def list_chats(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[Chat]:
    rows = await session.scalars(
        select(Chat).where(Chat.user_id == user.id).order_by(Chat.created_at.desc())
    )
    return list(rows)


@router.get("/{chat_id}", response_model=ChatDetail)
async def get_chat(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Chat:
    chat = await session.scalar(
        select(Chat)
        .where(Chat.id == chat_id)
        .options(
            selectinload(Chat.documents),
            selectinload(Chat.agent_runs),
            selectinload(Chat.messages),
            selectinload(Chat.report),
        )
    )
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status_code=404, detail="chat not found")
    return chat


@router.post("/{chat_id}/documents", response_model=DocumentOut)
async def upload_document(
    chat_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ChatDocument:
    await _load_owned_chat(session, chat_id, user)
    raw = await file.read()
    text = raw.decode("utf-8", errors="replace")
    doc = ChatDocument(
        chat_id=chat_id,
        filename=file.filename or "document.txt",
        content_type=file.content_type,
        text=text,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


@router.post("/{chat_id}/items")
async def submit_item(
    chat_id: str,
    body: SubmitItem,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    chat = await _load_owned_chat(session, chat_id, user)
    chat.idea = body.idea
    chat.status = ChatStatus.created
    await session.commit()

    registry = getattr(request.app.state, "agents", None)
    task = asyncio.create_task(run_council(chat_id, registry))
    _pipeline_tasks.add(task)
    task.add_done_callback(_pipeline_tasks.discard)
    return {"status": "started", "chat_id": chat_id}


@router.get("/{chat_id}/result", response_model=ReportOut)
async def get_result(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CouncilReport:
    await _load_owned_chat(session, chat_id, user)
    report = await session.scalar(select(CouncilReport).where(CouncilReport.chat_id == chat_id))
    if report is None:
        raise HTTPException(status_code=404, detail="report not ready")
    return report
