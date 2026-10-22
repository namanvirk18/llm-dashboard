from fastapi import APIRouter

from llm_dashboard.deps import ModelServiceDep
from llm_dashboard.schemas import ModelList, ModelOut, ModelPullOut, ModelPullRequest

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=ModelList)
def list_models(service: ModelServiceDep) -> ModelList:
    return ModelList(models=[ModelOut.model_validate(m) for m in service.list_models()])


@router.post("/pull", response_model=ModelPullOut)
def pull_model(body: ModelPullRequest, service: ModelServiceDep) -> ModelPullOut:
    return ModelPullOut.model_validate(service.pull(body.name))
