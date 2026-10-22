from fastapi import APIRouter

from llm_dashboard.deps import ConfigDep

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(config: ConfigDep) -> dict[str, object]:
    return {"status": "ok", "mock_mode": config.mock_mode}
