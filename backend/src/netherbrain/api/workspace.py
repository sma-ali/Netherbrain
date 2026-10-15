"""Parcourir le dossier atteignable, pour choisir le dossier d'un nouveau projet."""

from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException

from netherbrain.api.deps import ReachDep
from netherbrain.projects.workspace import FolderNotFoundError, WorkspaceError
from netherbrain.schemas import DirectoryListing, FolderInfo

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


@router.get("/directories")
async def list_directories(workspace: ReachDep, path: str = "") -> DirectoryListing:
    """Les sous-dossiers de `path`, un chemin relatif au dossier atteignable ("" : la racine)."""
    try:
        entries = workspace.list_directories(path)
    except FolderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    current = workspace.relative(workspace.resolve(path))
    parent = None if current == "" else PurePosixPath(current).parent.as_posix()
    return DirectoryListing(
        root=str(workspace.root),
        path=current,
        # PurePosixPath("a").parent vaut « . » : c'est la racine, notée "".
        parent="" if parent == "." else parent,
        directories=[FolderInfo.model_validate(entry) for entry in entries],
    )
