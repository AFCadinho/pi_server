import logging
import json
import subprocess
from time import perf_counter
import urllib.error
import urllib.request
from dataclasses import dataclass

from config import ProjectConfig, settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


class DeployError(Exception):
    def __init__(self, message: str, command_result: CommandResult | None = None):
        super().__init__(message)
        self.command_result = command_result


class DiscordNotifyError(Exception):
    pass


def _format_command(command: list[str]) -> str:
    return " ".join(command)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


def _run(command: list[str], project: ProjectConfig) -> CommandResult:
    logger.info("Running command for %s: %s", project.name, _format_command(command))

    try:
        completed = subprocess.run(
            command,
            cwd=project.path,
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError as exc:
        raise DeployError(f"Command not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise DeployError(f"Command timed out: {_format_command(command)}") from exc

    result = CommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )

    if result.stdout:
        logger.info("stdout: %s", result.stdout)
    if result.stderr:
        logger.warning("stderr: %s", result.stderr)

    if result.returncode != 0:
        raise DeployError(
            f"Command failed with exit code {result.returncode}: {_format_command(command)}",
            command_result=result,
        )

    return result


def notify_discord(
    project: ProjectConfig,
    status: str,
    message: str,
    duration_seconds: float | None = None,
    command_result: CommandResult | None = None,
    raise_errors: bool = False,
) -> None:
    if not settings.discord_webhook_url:
        return

    is_success = status == "succeeded"
    fields = [
        {"name": "Project", "value": project.name, "inline": True},
        {"name": "Branch", "value": project.branch, "inline": True},
        {"name": "Path", "value": str(project.path), "inline": False},
    ]

    if duration_seconds is not None:
        fields.append(
            {
                "name": "Duration",
                "value": f"{duration_seconds:.1f}s",
                "inline": True,
            }
        )

    if command_result:
        fields.append(
            {
                "name": "Command",
                "value": f"`{_truncate(_format_command(command_result.command), 1000)}`",
                "inline": False,
            }
        )
        if command_result.stderr:
            fields.append(
                {
                    "name": "stderr",
                    "value": f"```text\n{_truncate(command_result.stderr, 990)}\n```",
                    "inline": False,
                }
            )
        elif command_result.stdout:
            fields.append(
                {
                    "name": "stdout",
                    "value": f"```text\n{_truncate(command_result.stdout, 990)}\n```",
                    "inline": False,
                }
            )

    payload = json.dumps(
        {
            "embeds": [
                {
                    "title": f"Deploy {status}: {project.name}",
                    "description": _truncate(message, 1500),
                    "color": 0x2ECC71 if is_success else 0xE74C3C,
                    "fields": fields,
                }
            ]
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        settings.discord_webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "deploy-api/0.1 (+https://bots.pokemonaetheronline.com)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            logger.info("Discord notification sent: HTTP %s", response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        message = f"HTTP {exc.code}: {_truncate(body, 500)}"
        logger.warning("Discord notification failed: %s", message)
        if raise_errors:
            raise DiscordNotifyError(message) from exc
    except urllib.error.URLError as exc:
        logger.warning("Discord notification failed: %s", exc)
        if raise_errors:
            raise DiscordNotifyError(str(exc)) from exc


def test_discord_notification() -> dict:
    if not settings.discord_webhook_url:
        return {"configured": False, "sent": False}

    project = ProjectConfig(
        name="deploy-api",
        path=settings.project_root,
        branch="main",
        compose_command=("docker", "compose"),
    )
    notify_discord(
        project,
        "succeeded",
        "Discord webhook test message from deploy API",
        duration_seconds=0,
        raise_errors=True,
    )
    return {"configured": True, "sent": True}


def deploy_project(project: ProjectConfig) -> dict:
    started_at = perf_counter()

    if not project.path.exists() or not project.path.is_dir():
        exc = DeployError(f"Project path does not exist: {project.path}")
        notify_discord(
            project,
            "failed",
            str(exc),
            duration_seconds=perf_counter() - started_at,
        )
        raise exc

    logger.info("Starting deploy for %s in %s", project.name, project.path)

    git_steps = [
        ["git", "fetch", "origin", project.branch],
        ["git", "checkout", project.branch],
        ["git", "pull", "--ff-only", "origin", project.branch],
    ]

    if project.deploy_command:
        steps = [
            *(git_steps if project.pull_before_command else []),
            list(project.deploy_command),
        ]
    else:
        steps = [
            *git_steps,
            [*project.compose_command, "down"],
            [*project.compose_command, "up", "-d", "--build"],
        ]

    completed_steps: list[CommandResult] = []

    try:
        for step in steps:
            completed_steps.append(_run(step, project))
    except DeployError as exc:
        logger.exception("Deploy failed for %s", project.name)
        notify_discord(
            project,
            "failed",
            str(exc),
            duration_seconds=perf_counter() - started_at,
            command_result=exc.command_result,
        )
        raise

    logger.info("Deploy completed for %s", project.name)
    duration_seconds = perf_counter() - started_at
    notify_discord(
        project,
        "succeeded",
        "Completed successfully",
        duration_seconds=duration_seconds,
    )

    return {
        "project": project.name,
        "status": "success",
        "duration_seconds": round(duration_seconds, 2),
        "steps": [
            {
                "command": result.command,
                "returncode": result.returncode,
            }
            for result in completed_steps
        ],
    }
