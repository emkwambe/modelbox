"""Operator commands for the appliance.

    docker compose --env-file .env -f docker/docker-compose.appliance.yml \\
        exec modelbox-backend python -m app.cli create-owner --email you@example.com

**create-owner** is how a production appliance gets its first account. There is
no seeded account, self-registration is off in production, and just-in-time
OIDC provisioning is off until an issuer is allowed, so without it nobody
could ever sign in (owner decision H3, Sprint 7).

* The password is **prompted for**, twice, and never taken as an argument: an
  argument is visible in the process table and kept in shell history.
  `--password-stdin` reads it from standard input instead, for automation,
  in the same way as `docker login --password-stdin`.
* It **refuses if any owner already exists** on the appliance. It bootstraps;
  it is not a way to mint a second owner around the product's own controls.
* The user it creates is the **appliance owner** (`is_appliance_owner`), the
  one account that reads appliance-scope audit events such as logins.

**designate-appliance-owner** is the same step for an appliance upgraded from
before v1.11.0, which has workspace owners but no appliance owner, so
`create-owner` refuses. It sets the flag on an existing account that is OWNER of
some workspace, refuses if an appliance owner already exists, and records
`APPLIANCE_OWNER_DESIGNATED` (owner decision, Sprint 7 Step 3).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from collections.abc import Callable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.metadata_store import User, Workspace, WorkspaceMember
from app.services import audit_log

MIN_PASSWORD_LENGTH = 12


class CreateOwnerRefused(Exception):
    """The command declined; the message says why and names no secret."""


async def owner_exists(session: AsyncSession) -> bool:
    """True if any workspace on the appliance has an OWNER."""
    row = (
        await session.execute(select(WorkspaceMember).where(WorkspaceMember.role == "OWNER").limit(1))
    ).scalar_one_or_none()
    return row is not None


async def create_owner(
    session: AsyncSession, email: str, password: str, workspace_name: str
) -> User:
    """Create the first user as OWNER of a new workspace, or refuse."""
    if await owner_exists(session):
        raise CreateOwnerRefused(
            "An owner already exists on this appliance. Ask an owner to add you."
        )
    if len(password) < MIN_PASSWORD_LENGTH:
        raise CreateOwnerRefused(
            f"The password must be at least {MIN_PASSWORD_LENGTH} characters."
        )
    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise CreateOwnerRefused(f"{email} already has an account.")

    user = User(email=email, hashed_password=hash_password(password), is_appliance_owner=True)
    session.add(user)
    await session.flush()
    workspace = Workspace(name=workspace_name)
    session.add(workspace)
    await session.flush()
    session.add(
        WorkspaceMember(workspace_id=workspace.workspace_id, user_id=user.user_id, role="OWNER")
    )
    await session.commit()
    await audit_log.record(
        action="MEMBER_ADDED",
        actor_user_id=user.user_id,
        actor_email=user.email,
        workspace_id=workspace.workspace_id,
        resource_type="user",
        resource_id=str(user.user_id),
        detail={"role": "OWNER", "via": "create-owner", "appliance_owner": True},
    )
    return user


async def appliance_owner_exists(session: AsyncSession) -> bool:
    """True if any account already holds the appliance-owner flag."""
    row = (
        await session.execute(select(User).where(User.is_appliance_owner.is_(True)).limit(1))
    ).scalar_one_or_none()
    return row is not None


async def designate_appliance_owner(session: AsyncSession, email: str) -> User:
    """Give an existing workspace OWNER the appliance-owner flag, or refuse."""
    if await appliance_owner_exists(session):
        raise CreateOwnerRefused("This appliance already has an appliance owner.")
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if user is None:
        raise CreateOwnerRefused(f"No account for {email}.")
    owns = (
        await session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.user_id == user.user_id, WorkspaceMember.role == "OWNER"
            ).limit(1)
        )
    ).scalar_one_or_none()
    if owns is None:
        raise CreateOwnerRefused(f"{email} is not the OWNER of any workspace.")
    user.is_appliance_owner = True
    await session.commit()
    await audit_log.record(
        action="APPLIANCE_OWNER_DESIGNATED",
        actor_user_id=user.user_id,
        actor_email=user.email,
        resource_type="user",
        resource_id=str(user.user_id),
        detail={"via": "designate-appliance-owner"},
    )
    return user


def read_password(from_stdin: bool, prompt: Callable[[str], str] = getpass.getpass) -> str:
    """The password from a prompt (entered twice) or from standard input."""
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = prompt("Password for the new owner: ")
    second = prompt("Repeat the password: ")
    if first != second:
        raise CreateOwnerRefused("The passwords did not match.")
    return first


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    owner = commands.add_parser("create-owner", help="Create the appliance's first owner.")
    owner.add_argument("--email", required=True)
    owner.add_argument("--workspace-name", default="Default Workspace")
    owner.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the password from standard input instead of prompting.",
    )
    designate = commands.add_parser(
        "designate-appliance-owner",
        help="Upgraded installs: make an existing workspace OWNER the appliance owner.",
    )
    designate.add_argument("--email", required=True)
    return parser


async def run(argv: Sequence[str] | None, session_factory: Callable[[], AsyncSession]) -> int:
    """The command: parse, dispatch, report. Returns the exit code.

    Separate from :func:`main` only so a test can drive the real command
    against its own database; ``main`` passes the appliance's session factory.
    """
    args = _parser().parse_args(argv)
    try:
        async with session_factory() as session:
            if args.command == "designate-appliance-owner":
                user = await designate_appliance_owner(session, args.email)
                print(f"{user.email} is now the appliance owner.")
                return 0
            password = read_password(args.password_stdin)
            user = await create_owner(session, args.email, password, args.workspace_name)
    except CreateOwnerRefused as exc:
        print(f"{args.command} refused: {exc}", file=sys.stderr)
        return 1
    print(f"Created owner {user.email} in workspace {args.workspace_name!r}.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    from app.core.database import get_sessionmaker

    return asyncio.run(run(argv, get_sessionmaker()))


if __name__ == "__main__":
    raise SystemExit(main())
