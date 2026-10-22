from fastapi import APIRouter, status

from llm_dashboard.deps import PluginServiceDep
from llm_dashboard.schemas import PluginInstallRequest, PluginList, PluginOut

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("", response_model=PluginList)
def list_plugins(service: PluginServiceDep) -> PluginList:
    return PluginList(plugins=[PluginOut.model_validate(p) for p in service.list_plugins()])


@router.post("", response_model=PluginOut, status_code=status.HTTP_201_CREATED)
def install_plugin(body: PluginInstallRequest, service: PluginServiceDep) -> PluginOut:
    return PluginOut.model_validate(service.install(body.name, body.version))
