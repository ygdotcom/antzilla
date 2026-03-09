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

    # v0 blocks until generation completes — can take 2-5 minutes
    async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30)) as client:
        logger.info("v0_chat_starting", prompt_len=len(prompt))
        resp = await client.post(
            f"{BASE_URL}/v1/chats",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info("v0_chat_created", chat_id=data.get("id"),
                     has_version=bool(data.get("latestVersion")),
                     files=len(data.get("files", [])))
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
    """Send a follow-up message to iterate on the app. Blocks until v0 finishes."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30)) as client:
        resp = await client.post(
            f"{BASE_URL}/v1/chats/{chat_id}/messages",
            headers=_headers(),
            json={"message": message},
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
    """High-level: create project + generate app + poll for completion + deploy.

    Returns {"project_id", "chat_id", "demo_url", "deployment_url", "files"}.
    """
    # Create project
    project = await create_project(name or "antzilla-biz")
    project_id = project.get("id", "")

    # Create chat — this returns immediately, generation happens async
    chat = await create_chat(prompt, project_id=project_id)
    chat_id = chat.get("id", "")
    web_url = chat.get("webUrl", chat.get("url", ""))

    logger.info("v0_chat_started", chat_id=chat_id, web_url=web_url)

    # Poll for completion — v0 generates code asynchronously
    # Check every 15s for up to 5 minutes
    version_id = ""
    demo_url = ""
    files = []

    for attempt in range(24):  # 24 * 15s = 6 minutes max
        await asyncio.sleep(15)
        try:
            chat_data = await get_chat(chat_id)
            latest_version = chat_data.get("latestVersion", {})
            version_id = latest_version.get("id", "")
            demo_url = chat_data.get("demo", "")
            files = chat_data.get("files", [])

            if version_id or demo_url or files:
                logger.info("v0_generation_complete", version_id=version_id,
                            demo_url=demo_url, files=len(files), attempts=attempt + 1)
                break

            # Check assistant messages for code content
            messages = chat_data.get("messages", [])
            for msg in messages:
                if msg.get("role") != "assistant":
                    continue
                # Check files on message
                if msg.get("files"):
                    files = msg["files"]
                    break
                # Check content for code parts
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 3000:
                    try:
                        import json as _json
                        parsed = _json.loads(content)
                        parts = parsed.get("parts", [])
                        has_code = any(
                            p.get("type") in ("code", "file", "component-preview")
                            for p in parts
                        )
                        if has_code:
                            logger.info("v0_code_found_in_content", attempts=attempt + 1)
                            break
                    except (ValueError, TypeError):
                        pass

            if files:
                break

            logger.info("v0_polling", attempt=attempt + 1, content_len=sum(
                len(m.get("content", "")) for m in messages if m.get("role") == "assistant"
            ))
        except Exception as exc:
            logger.warning("v0_poll_error", attempt=attempt + 1, error=str(exc))

    # Deploy if we have a version
    deployment = {}
    deployment_url = demo_url
    if project_id and chat_id and version_id:
        try:
            deployment = await deploy(project_id, chat_id, version_id)
            deployment_url = deployment.get("url", demo_url)
        except Exception as exc:
            logger.warning("v0_deploy_failed", error=str(exc))

    # If no deployment URL, use the v0 web URL as fallback
    if not deployment_url and web_url:
        deployment_url = web_url

    return {
        "project_id": project_id,
        "chat_id": chat_id,
        "version_id": version_id,
        "demo_url": demo_url or web_url,
        "deployment_url": deployment_url,
        "web_url": web_url,
        "files": files,
        "file_count": len(files),
    }
