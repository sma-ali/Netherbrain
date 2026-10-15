"""Routes des projets : un dossier de code, auquel on rattache des conversations."""

import uuid

from fastapi import APIRouter, HTTPException, status

from netherbrain.api.deps import DbSession, ReachDep, WorkspaceDep
from netherbrain.db.models import Project
from netherbrain.db.repository import ProjectRepository
from netherbrain.projects.workspace import (
    Workspace,
    WorkspaceError,
    git_branch,
    instructions_file,
    locate_project,
)
from netherbrain.schemas import CreateProjectRequest, ProjectOut

router = APIRouter(prefix="/api/projects", tags=["projects"])


def describe(project: Project, reach: Workspace, workspace: Workspace) -> ProjectOut:
    """La fiche d'un projet, complétée par ce qu'on lit dans son dossier à l'instant."""
    folder = locate_project(project.path, reach, workspace)
    instructions = instructions_file(folder) if folder else None
    return ProjectOut(
        id=project.id,
        name=project.name,
        path=str(folder) if folder else project.path,
        created_at=project.created_at,
        available=folder is not None,
        git_branch=git_branch(folder) if folder else None,
        instructions_file=instructions.name if instructions else None,
    )


@router.get("")
async def list_projects(
    session: DbSession, reach: ReachDep, workspace: WorkspaceDep
) -> list[ProjectOut]:
    """Les projets, par ordre alphabétique."""
    projects = await ProjectRepository(session).list_all()
    return [describe(p, reach, workspace) for p in projects]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    request: CreateProjectRequest, session: DbSession, reach: ReachDep, workspace: WorkspaceDep
) -> ProjectOut:
    """Fait d'un dossier un projet. `request.path` est relatif au dossier atteignable.

    Créer le projet, c'est approuver ce dossier : l'agent pourra le lire sans demander (mais
    pas y écrire, ni y lancer de commande, sans votre accord).
    """
    try:
        folder = reach.directory(request.path)
    except WorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if folder == reach.root:
        # Le dossier atteignable entier ouvrirait tous vos dossiers à la lecture, sans accord.
        raise HTTPException(status_code=400, detail="Pick a folder inside your home folder")

    # Le chemin absolu et normalisé (sans « .. » ni lien) : c'est lui qui doit être unique.
    # Un ancien projet peut désigner le même dossier par un chemin relatif.
    paths = [str(folder)]
    if folder.is_relative_to(workspace.root):
        paths.append(workspace.relative(folder))
    repository = ProjectRepository(session)
    for path in paths:
        if await repository.get_by_path(path) is not None:
            raise HTTPException(status_code=409, detail="This folder already belongs to a project")

    name = (request.name or "").strip() or folder.name
    project = await repository.create(name=name, path=str(folder))
    await session.commit()
    return describe(project, reach, workspace)


@router.get("/{project_id}")
async def get_project(
    project_id: uuid.UUID, session: DbSession, reach: ReachDep, workspace: WorkspaceDep
) -> ProjectOut:
    project = await ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return describe(project, reach, workspace)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: uuid.UUID, session: DbSession) -> None:
    """Oublie le projet. Ses conversations restent, et son dossier n'est jamais touché."""
    if not await ProjectRepository(session).delete(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    await session.commit()
