"""Workspace members: add, change role, remove (Sprint 8 Step 6, owner decisions).

An OWNER or ADMIN adds an **existing** appliance user to a workspace, changes a
member's role, or removes a member. Creating users stays with OIDC, SCIM and
``create-owner``: an email with no user is refused, naming those three.

The rules, each enforced here and each with its own test:

* **No one grants a role above their own**, and an ADMIN cannot make an OWNER.
  The role acted with is the effective one: an API key acts at the lower of
  its cap and its creator's current role (``dependencies.effective_role``).
* **No one changes or removes a member whose role is above their own**, so an
  ADMIN cannot demote or remove an OWNER.
* **The last OWNER of a workspace can never be demoted or removed.** The
  owners are read under a row lock, so two concurrent demotions cannot leave
  a workspace with none.

A removed or demoted member's API keys lose that access at once: every
request re-reads the key's creator's membership (``dependencies._authorize``).

Each change is an audit event (MEMBER_ADDED, MEMBER_ROLE_CHANGED,
MEMBER_REMOVED) written in the change's own transaction.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select

from app.api.v1.dependencies import (
    _ROLE_LEVEL,
    CurrentUserDep,
    SessionDep,
    effective_role,
    principal_of,
    require_membership,
    require_resource_role,
)
from app.models.metadata_store import AuditEvent, User, Workspace, WorkspaceMember
from app.schemas.data_model import MemberAddRequest, MemberInfo, MemberUpdateRequest

router = APIRouter(prefix="/workspaces", tags=["members"])

ViewerWorkspace = Annotated[Workspace, Depends(require_resource_role("VIEWER", Workspace, "workspace_id", "path"))]
AdminWorkspace = Annotated[Workspace, Depends(require_resource_role("ADMIN", Workspace, "workspace_id", "path"))]

CREATE_USERS_ELSEWHERE = ("Users are created by OIDC sign-in, SCIM provisioning or `create-owner`; "
                          "this adds existing users only.")


def _level(role: str) -> int:
    return _ROLE_LEVEL.get(role, 0)


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def check_grant(actor_role: str, new_role: str) -> None:
    """Refuse a grant above the actor's own role; name the ADMIN-to-OWNER case."""
    if actor_role == "ADMIN" and new_role == "OWNER":
        raise _forbidden("An ADMIN cannot make an OWNER.")
    if _level(new_role) > _level(actor_role):
        raise _forbidden(f"You cannot grant a role above your own ({actor_role}).")


def check_target(actor_role: str, target_role: str) -> None:
    """Refuse acting on a member whose role is above the actor's own."""
    if _level(target_role) > _level(actor_role):
        raise _forbidden(f"You cannot change or remove a member whose role ({target_role}) is above your own "
                         f"({actor_role}).")


async def _actor_role(request: Request, session: SessionDep, user: User, workspace: Workspace) -> str:
    member = await require_membership(session, user.user_id, workspace.workspace_id)
    return effective_role(member.role, principal_of(request))


async def _member(session: SessionDep, workspace: Workspace, user_id: uuid.UUID) -> WorkspaceMember:
    member = (await session.execute(select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace.workspace_id, WorkspaceMember.user_id == user_id))
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such member of this workspace.")
    return member


async def _refuse_last_owner(session: SessionDep, workspace: Workspace, member: WorkspaceMember) -> None:
    """The workspace's last OWNER cannot stop being one. Owners are locked
    while counted, so concurrent demotions are serialised (PostgreSQL)."""
    if member.role != "OWNER":
        return
    owners = (await session.execute(
        select(WorkspaceMember.membership_id)
        .where(WorkspaceMember.workspace_id == workspace.workspace_id, WorkspaceMember.role == "OWNER")
        .with_for_update())).all()
    if len(owners) <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="The last OWNER of a workspace cannot be demoted or removed.")


def _audit(session: SessionDep, action: str, actor: User, workspace: Workspace, target: User,
           **detail: object) -> None:
    session.add(AuditEvent(
        action=action, outcome="SUCCESS", scope="workspace", actor_user_id=actor.user_id,
        actor_email=actor.email, workspace_id=workspace.workspace_id, resource_type="user",
        resource_id=str(target.user_id), detail={"member": target.email, "via": "members-api", **detail},
    ))


async def _info(session: SessionDep, workspace: Workspace) -> list[MemberInfo]:
    rows = (await session.execute(
        select(User.user_id, User.email, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.user_id)
        .where(WorkspaceMember.workspace_id == workspace.workspace_id)
        .order_by(User.email))).all()
    return [MemberInfo(user_id=u, email=e, role=r) for u, e, r in rows]


@router.get("/{workspace_id}/members", response_model=list[MemberInfo], summary="The workspace's members")
async def list_members(session: SessionDep, workspace: ViewerWorkspace) -> list[MemberInfo]:
    return await _info(session, workspace)


@router.post("/{workspace_id}/members", response_model=list[MemberInfo], status_code=status.HTTP_201_CREATED,
             summary="Add an existing user to the workspace (OWNER or ADMIN)")
async def add_member(payload: MemberAddRequest, request: Request, session: SessionDep, user: CurrentUserDep,
                     workspace: AdminWorkspace) -> list[MemberInfo]:
    actor_role = await _actor_role(request, session, user, workspace)
    check_grant(actor_role, payload.role)
    email = payload.email.strip()
    target = (await session.execute(select(User).where(func.lower(User.email) == email.lower()))
              ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"No user with the email {email!r} exists on this appliance. "
                                   f"{CREATE_USERS_ELSEWHERE}")
    existing = (await session.execute(select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace.workspace_id, WorkspaceMember.user_id == target.user_id))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"{target.email} is already a member, as {existing.role}; change the role "
                                   "instead.")
    session.add(WorkspaceMember(workspace_id=workspace.workspace_id, user_id=target.user_id, role=payload.role))
    _audit(session, "MEMBER_ADDED", user, workspace, target, role=payload.role)
    await session.flush()
    return await _info(session, workspace)


@router.patch("/{workspace_id}/members/{user_id}", response_model=list[MemberInfo],
              summary="Change a member's role (OWNER or ADMIN)")
async def change_role(user_id: uuid.UUID, payload: MemberUpdateRequest, request: Request, session: SessionDep,
                      user: CurrentUserDep, workspace: AdminWorkspace) -> list[MemberInfo]:
    actor_role = await _actor_role(request, session, user, workspace)
    member = await _member(session, workspace, user_id)
    check_target(actor_role, member.role)
    check_grant(actor_role, payload.role)
    if payload.role != member.role:
        if payload.role != "OWNER":
            await _refuse_last_owner(session, workspace, member)
        target = await session.get(User, user_id)
        assert target is not None  # the membership's foreign key
        _audit(session, "MEMBER_ROLE_CHANGED", user, workspace, target, previous=member.role, role=payload.role)
        member.role = payload.role
        await session.flush()
    return await _info(session, workspace)


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Remove a member (OWNER or ADMIN)")
async def remove_member(user_id: uuid.UUID, request: Request, session: SessionDep, user: CurrentUserDep,
                        workspace: AdminWorkspace) -> Response:
    """The member's API keys for this workspace stop working at once: each
    request re-reads the creator's membership, and there is none."""
    actor_role = await _actor_role(request, session, user, workspace)
    member = await _member(session, workspace, user_id)
    check_target(actor_role, member.role)
    await _refuse_last_owner(session, workspace, member)
    target = await session.get(User, user_id)
    assert target is not None  # the membership's foreign key
    _audit(session, "MEMBER_REMOVED", user, workspace, target, previous=member.role)
    await session.delete(member)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
