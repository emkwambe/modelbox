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

    user = User(email=email, hashed_password=hash_password(password))
    session.add(user)
    await session.flush()
    workspace = Workspace(name=workspace_name)
    session.add(workspace)
    await session.flush()
    session.add(
        WorkspaceMember(workspace_id=workspace.workspace_id, user_id=user.user_id, role="OWNER")
    )
    await session.commit()
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
    return parser


async def _run_create_owner(email: str, password: str, workspace_name: str) -> User:
    from app.core.database import get_sessionmaker

    async with get_sessionmaker()() as session:
        return await create_owner(session, email, password, workspace_name)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        password = read_password(args.password_stdin)
        user = asyncio.run(_run_create_owner(args.email, password, args.workspace_name))
    except CreateOwnerRefused as exc:
        print(f"create-owner refused: {exc}", file=sys.stderr)
        return 1
    print(f"Created owner {user.email} in workspace {args.workspace_name!r}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
