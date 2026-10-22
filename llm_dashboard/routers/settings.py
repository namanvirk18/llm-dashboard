from fastapi import APIRouter

from llm_dashboard.deps import SettingsStoreDep
from llm_dashboard.schemas import SettingsOut, SettingsUpdate
from llm_dashboard.services.settings import StoredSettings

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _view(settings: StoredSettings) -> SettingsOut:
    """Never expose the stored API key, only whether one is set."""
    return SettingsOut(
        provider=settings.provider,
        model=settings.model,
        base_url=settings.base_url,
        api_key_set=bool(settings.api_key),
        update_channel=settings.update_channel,
    )


@router.get("", response_model=SettingsOut)
def get_settings(store: SettingsStoreDep) -> SettingsOut:
    return _view(store.load())


@router.put("", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, store: SettingsStoreDep) -> SettingsOut:
    return _view(store.update(body.model_dump(exclude_unset=True)))
