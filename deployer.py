import logging
import json
import subprocess
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


def _run(command: list[str], project: ProjectConfig) -> CommandResult:
    logger.info("Running command for %s: %s", project.name, " ".join(command))

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
        raise DeployError(f"Command timed out: {' '.join(command)}") from exc

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
            f"Command failed with exit code {result.returncode}: {' '.join(command)}",
            command_result=result,
        )

    return result


def notify_discord(project_name: str, status: str, message: str) -> None:
    if not settings.discord_webhook_url:
        return

    payload = json.dumps(
        {"content": f"Deploy `{project_name}` {status}: {message[:1500]}"}
    ).encode("utf-8")
    request = urllib.request.Request(
        settings.discord_webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            logger.info("Discord notification sent: HTTP %s", response.status)
    except urllib.error.URLError as exc:
        logger.warning("Discord notification failed: %s", exc)


def deploy_project(project: ProjectConfig) -> dict:
    if not project.path.exists() or not project.path.is_dir():
        raise DeployError(f"Project path does not exist: {project.path}")

    logger.info("Starting deploy for %s in %s", project.name, project.path)

    steps = [
        ["git", "fetch", "origin", project.branch],
        ["git", "checkout", project.branch],
        ["git", "pull", "--ff-only", "origin", project.branch],
        [*project.compose_command, "down"],
        [*project.compose_command, "up", "-d", "--build"],
    ]

    completed_steps: list[CommandResult] = []

    try:
        for step in steps:
            completed_steps.append(_run(step, project))
    except DeployError as exc:
        logger.exception("Deploy failed for %s", project.name)
        notify_discord(project.name, "failed", str(exc))
        raise

    logger.info("Deploy completed for %s", project.name)
    notify_discord(project.name, "succeeded", "completed successfully")

    return {
        "project": project.name,
        "status": "success",
        "steps": [
            {
                "command": result.command,
                "returncode": result.returncode,
            }
            for result in completed_steps
        ],
    }
