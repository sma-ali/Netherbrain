"""Routes des projets : un dossier de code, auquel on rattache des conversations."""

import uuid

from fastapi import APIRouter, HTTPException, status

from netherbrain.api.deps import DbSession, WorkspaceDep
from netherbrain.db.models import Project
from netherbrain.db.repository import ProjectRepository
from netherbrain.projects.workspace import Workspace, WorkspaceError, git_branch, instructions_file
from netherbrain.schemas import CreateProjectRequest, ProjectOut

router = APIRouter(prefix="/api/projects", tags=["projects"])


def describe(project: Project, workspace: Workspace) -> ProjectOut:
    """La fiche d'un projet, complétée par ce qu'on lit dans son dossier à l'instant."""
    folder = workspace.find(project.path)
    instructions = instructions_file(folder) if folder else None
    return ProjectOut(
        id=project.id,
        name=project.name,
        path=project.path,
        created_at=project.created_at,
        available=folder is not None,
        git_branch=git_branch(folder) if folder else None,
        instructions_file=instructions.name if instructions else None,
    )


@router.get("")
async def list_projects(session: DbSession, workspace: WorkspaceDep) -> list[ProjectOut]:
    """Les projets, par ordre alphabétique."""
    return [describe(p, workspace) for p in await ProjectRepository(session).list_all()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    request: CreateProjectRequest, session: DbSession, workspace: WorkspaceDep
) -> ProjectOut:
    try:
        folder = workspace.directory(request.path)
    except WorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if folder == workspace.root:
        # Le dossier de travail entier donnerait accès à tous les projets à la fois.
        raise HTTPException(status_code=400, detail="Pick a folder inside the workspace")

    # Le chemin normalisé (« a/../b » devient « b ») : c'est lui qui doit être unique.
    path = workspace.relative(folder)
    repository = ProjectRepository(session)
    if await repository.get_by_path(path) is not None:
        raise HTTPException(status_code=409, detail="This folder already belongs to a project")

    name = (request.name or "").strip() or folder.name
    project = await repository.create(name=name, path=path)
    await session.commit()
    return describe(project, workspace)


@router.get("/{project_id}")
async def get_project(
    project_id: uuid.UUID, session: DbSession, workspace: WorkspaceDep
) -> ProjectOut:
    project = await ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return describe(project, workspace)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: uuid.UUID, session: DbSession) -> None:
    """Oublie le projet. Ses conversations restent, et son dossier n'est jamais touché."""
    if not await ProjectRepository(session).delete(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    await session.commit()
