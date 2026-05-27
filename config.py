import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
PROJECTS_FILE = Path(os.getenv("PROJECTS_FILE", BASE_DIR / "projects.json"))


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    path: Path
    branch: str
    compose_command: tuple[str, ...]
    deploy_command: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Settings:
    deploy_token: str
    discord_webhook_url: str | None


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


settings = Settings(
    deploy_token=_required_env("DEPLOY_TOKEN"),
    discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL") or None,
)


def _load_projects(path: Path) -> dict[str, ProjectConfig]:
    if not path.exists():
        raise RuntimeError(f"Projects config file not found: {path}")

    with path.open(encoding="utf-8") as file:
        raw_projects = json.load(file)

    if not isinstance(raw_projects, dict):
        raise RuntimeError("Projects config must be a JSON object")

    projects: dict[str, ProjectConfig] = {}
    for name, raw_project in raw_projects.items():
        if not isinstance(name, str) or not name:
            raise RuntimeError("Project names must be non-empty strings")
        if not isinstance(raw_project, dict):
            raise RuntimeError(f"Project config for {name} must be an object")

        project_path = raw_project.get("path")
        branch = raw_project.get("branch", "main")
        compose_command = raw_project.get("compose_command", ["docker", "compose"])
        deploy_command = raw_project.get("deploy_command")

        if not isinstance(project_path, str) or not project_path:
            raise RuntimeError(f"Project {name} must have a non-empty path")
        if not isinstance(branch, str) or not branch:
            raise RuntimeError(f"Project {name} must have a non-empty branch")
        if (
            not isinstance(compose_command, list)
            or not compose_command
            or not all(isinstance(part, str) and part for part in compose_command)
        ):
            raise RuntimeError(
                f"Project {name} compose_command must be a non-empty string list"
            )
        if deploy_command is not None and (
            not isinstance(deploy_command, list)
            or not deploy_command
            or not all(isinstance(part, str) and part for part in deploy_command)
        ):
            raise RuntimeError(
                f"Project {name} deploy_command must be a non-empty string list"
            )

        projects[name] = ProjectConfig(
            name=name,
            path=Path(project_path),
            branch=branch,
            compose_command=tuple(compose_command),
            deploy_command=tuple(deploy_command) if deploy_command else None,
        )

    return projects


# Only projects listed in this file can be deployed.
PROJECTS = _load_projects(PROJECTS_FILE)
