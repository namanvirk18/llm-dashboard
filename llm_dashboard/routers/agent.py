from fastapi import APIRouter, Request

from llm_dashboard.agent.llm import create_llm_client
from llm_dashboard.agent.loop import Agent
from llm_dashboard.agent.tools import ToolBox, list_workspace_files
from llm_dashboard.deps import ConfigDep, SettingsStoreDep
from llm_dashboard.schemas import AgentRequest, AgentRunOut, WorkspaceFiles

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/summarize", response_model=AgentRunOut)
def summarize(
    body: AgentRequest, request: Request, config: ConfigDep, store: SettingsStoreDep
) -> AgentRunOut:
    llm = create_llm_client(config, store.load(), request.app.state.llm_transport)
    tools = ToolBox(config.workspace_dir, request.app.state.http_client)
    return AgentRunOut.model_validate(Agent(llm, tools).summarise(body.target))


@router.get("/workspace", response_model=WorkspaceFiles)
def workspace_files(config: ConfigDep) -> WorkspaceFiles:
    return WorkspaceFiles(files=list_workspace_files(config.workspace_dir))
