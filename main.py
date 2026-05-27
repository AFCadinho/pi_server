import logging
from secrets import compare_digest

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from config import PROJECTS, settings
from deployer import DeployError, deploy_project


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Raspberry Pi Deploy API")


def require_bearer_token(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not compare_digest(token, settings.deploy_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid bearer token",
        )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/projects", dependencies=[Depends(require_bearer_token)])
def list_projects() -> dict:
    return {"projects": sorted(PROJECTS.keys())}


@app.post("/deploy/{project_name}", dependencies=[Depends(require_bearer_token)])
async def deploy(project_name: str) -> dict:
    project = PROJECTS.get(project_name)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown project",
        )

    try:
        # Deploy commands are blocking, so run them outside the event loop.
        return await run_in_threadpool(deploy_project, project)
    except DeployError as exc:
        logger.exception("Deploy endpoint failed for %s", project_name)
        payload = {"detail": str(exc)}
        if exc.command_result:
            payload["command"] = exc.command_result.command
            payload["stderr"] = exc.command_result.stderr
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=payload,
        ) from exc
