"""v0 Platform API client — text-to-app generation via Vercel's v0.

Endpoints:
- POST /v1/projects — create project
- POST /v1/chats — create chat (generates app from prompt)
- POST /v1/chats/:id/messages — send follow-up message
- GET /v1/chats/:id/messages — get messages with generated files
- POST /v1/deployments — deploy project
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

from src.config import settings

logger = structlog.get_logger()

BASE_URL = "https://api.v0.dev"


def _headers() -> dict:
    key = settings.get("V0_API_KEY")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


async def create_project(name: str) -> dict:
    """Create a new v0 project."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}/v1/projects",
            headers=_headers(),
            json={"name": name},
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info("v0_project_created", id=data.get("id"), name=name)
        return data


async def create_chat(prompt: str, project_id: str | None = None) -> dict:
    """Create a chat — v0 generates an app from the prompt.

    Returns chat object with id, files, demo URL, etc.
    v0 streams the response — generation can take 60-180 seconds.
    """
    payload: dict = {"message": prompt}
    if project_id:
        payload["projectId"] = project_id

    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(
            f"{BASE_URL}/v1/chats",
            headers=_headers(),
            json=payload,
        )
        if resp.status_code == 422:
            # Try alternative field name
            payload2 = {"initialMessage": prompt}
            if project_id:
                payload2["projectId"] = project_id
            resp = await client.post(
                f"{BASE_URL}/v1/chats",
                headers=_headers(),
                json=payload2,
            )
        resp.raise_for_status()
        data = resp.json()
        logger.info("v0_chat_created", chat_id=data.get("id"))
        return data


async def init_chat_with_files(files: list[dict], project_id: str | None = None,
                                initial_context: str = "") -> dict:
    """Initialize a chat with existing files (faster, no token cost for init)."""
    payload = {
        "type": "files",
        "files": files,
    }
    if project_id:
        payload["projectId"] = project_id
    if initial_context:
        payload["initialContext"] = initial_context

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{BASE_URL}/v1/chats/init",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def send_message(chat_id: str, message: str) -> dict:
    """Send a follow-up message to iterate on the app."""
    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(
            f"{BASE_URL}/v1/chats/{chat_id}/messages",
            headers=_headers(),
            json={"content": message},
        )
        resp.raise_for_status()
        return resp.json()


async def get_messages(chat_id: str) -> list[dict]:
    """Get all messages in a chat (includes generated files)."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{BASE_URL}/v1/chats/{chat_id}/messages",
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json().get("data", [])


async def get_chat(chat_id: str) -> dict:
    """Get chat details including latest version and files."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{BASE_URL}/v1/chats/{chat_id}",
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def deploy(project_id: str, chat_id: str, version_id: str) -> dict:
    """Deploy a project to v0's hosting."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{BASE_URL}/v1/deployments",
            headers=_headers(),
            json={
                "projectId": project_id,
                "chatId": chat_id,
                "versionId": version_id,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info("v0_deployed", url=data.get("url"))
        return data


async def build_app(prompt: str, name: str = "") -> dict:
    """High-level: create project + generate app + get files + deploy.

    Returns {"project_id", "chat_id", "demo_url", "deployment_url", "files"}.
    """
    # Create project
    project = await create_project(name or "antzilla-biz")
    project_id = project.get("id", "")

    # Generate app from prompt
    chat = await create_chat(prompt, project_id=project_id)
    chat_id = chat.get("id", "")

    # Wait for generation to complete and get the chat with files
    await asyncio.sleep(5)
    chat_data = await get_chat(chat_id)

    # Get demo URL
    demo_url = chat_data.get("demo", "")
    latest_version = chat_data.get("latestVersion", {})
    version_id = latest_version.get("id", "")

    # Get generated files
    files = chat_data.get("files", [])

    # Deploy
    deployment = {}
    if project_id and chat_id and version_id:
        try:
            deployment = await deploy(project_id, chat_id, version_id)
        except Exception as exc:
            logger.warning("v0_deploy_failed", error=str(exc))

    deployment_url = deployment.get("url", demo_url)

    return {
        "project_id": project_id,
        "chat_id": chat_id,
        "version_id": version_id,
        "demo_url": demo_url,
        "deployment_url": deployment_url,
        "files": files,
        "file_count": len(files),
    }
