# Availability, backup and restore

*The appliance's honest availability position (register G12). Written
2026-09-02. Every number here is either a measurement or a stated limitation —
there are no targets in this document that nothing has been tested against.*

**This is not a high-availability claim, and it is deliberately not written as
one.** ModelBox AI is a single-node Docker appliance. It has no clustering, no
automatic failover, and no replica. A reviewer who needs an HA answer should get
"no" from this page in the first paragraph rather than after three.

What a single-node deployment *can* offer is a bounded, tested recovery — and
that is a reviewable answer. Silence is not.

---

## The shape of the deployment

Six services, of which **two hold state that matters** and one holds state that
does not:

| Service | State | If it is lost |
| :-- | :-- | :-- |
| `postgres-db` | **All of it.** Users, workspaces, models, entities, columns, relationships, jobs, connections, API keys, trainer progress, the egress ledger, the audit trail | Everything. This is the backup target |
| `ollama-engine` (air-gap only) | Downloaded model weights | Re-pullable, but not over an air gap — treat as a restore input, not as data |
| `redis-cache` | Job queue and cache | Nothing durable. In-flight synthesis jobs are lost and must be re-run |
| `modelbox-api`, `modelbox-worker`, `modelbox-ui`, `litellm-proxy` | None | Nothing |

So the recovery question is a single question: **can `postgres-db` be restored
from a dump into a new volume, at a revision the application will start
against.**

---

## The position

| | |
| :-- | :-- |
| **Architecture** | Single node. No HA, no failover, no replica |
| **RPO** — data you can lose | **Your backup interval.** The appliance takes no backups of its own; the operator schedules `pg_dump`. At the recommended nightly cadence, up to 24 hours |
| **RTO** — time to be running again | **Minutes, bounded by the restore and by your ability to obtain the images.** The verified restore below completes in well under a minute on a laptop against a small database; the honest constraint is image availability in an air-gapped estate, not the database |
| **Failure modes not covered** | Host loss with no off-host backup. Volume corruption with no backup. A hardware failure during a synthesis job loses that job |

**RPO is the operator's choice and we should say so plainly rather than quote a
number we do not control.** An appliance that claims a 24-hour RPO while taking
no backups is claiming something about a cron job somebody else has to write.

---

## What has actually been tested

`backend/scripts/verify_restore.py`, run on demand. It is a script rather than a
runbook because a restore that is expensive to re-test is a restore nobody
re-tests, and this one has to be re-run whenever a migration lands.

The loop:

1. Start PostgreSQL 16 — the same image the appliance ships.
2. Bring it to head with the **real** Alembic migrations.
3. Write a known row.
4. `pg_dump`.
5. **Destroy the container and its volume entirely.**
6. Start a new database, restore the dump, and verify.

**Step 5 is the whole point.** A restore tested by dropping a table proves the
dump contains that table. A restore tested by destroying the volume proves the
dump is sufficient on its own, which is the claim an operator actually needs.

**Step 6 checks two things, and the second is the one that matters.** The row is
the obvious assertion. The Alembic revision is the one that catches the real
failure: a database restored at the wrong revision accepts connections, serves
reads, and then fails the *next* deployment — so the damage surfaces days later
and looks like a release problem.

### Result, 2026-09-02

```
1. starting a database
2. migrating to head
   at revision 0017_extend_roles
3. writing a known row
4. pg_dump
   899 lines, 29766 bytes
5. destroying the database AND its volume
6. restoring into a new database
   marker rows: 1 (want 1)
   revision:    0017_extend_roles (want 0017_extend_roles)
RESTORE VERIFIED
```

Docker 29.6.1, `postgres:16-alpine`, Windows host. Exit code 0.

---

## Operator runbook

### Back up

```bash
docker compose -f docker/docker-compose.appliance.yml exec -T postgres-db \
  pg_dump -U modelbox -d modelbox_metadata > modelbox-$(date +%F).sql
```

Nightly is the recommended cadence. **Store it off the host** — a backup on the
volume you are protecting against is not a backup.

Two things the dump does *not* contain, and both will stop a restore being a
recovery:

- **`ENCRYPTION_KEY` from `.env`.** Connection secrets are encrypted with it. A
  database restored without the original key gives you every row and no usable
  warehouse connection.
- **Ollama model weights**, in air-gapped installs. They are re-pullable on a
  connected host and are not re-pullable on the host that most needs them.

### Restore

```bash
docker compose -f docker/docker-compose.appliance.yml down
docker volume rm modelbox_pgdata
docker compose -f docker/docker-compose.appliance.yml up -d postgres-db
docker compose -f docker/docker-compose.appliance.yml exec -T postgres-db \
  psql -U modelbox -d modelbox_metadata < modelbox-2026-09-02.sql
docker compose -f docker/docker-compose.appliance.yml up -d
```

Then verify the revision matches the release you are running:

```bash
docker compose -f docker/docker-compose.appliance.yml exec -T postgres-db \
  psql -U modelbox -d modelbox_metadata -tAc \
  "SELECT version_num FROM alembic_version"
```

### Re-test after every migration

```bash
cd backend && .venv/Scripts/python -m scripts.verify_restore
```

A migration that breaks restorability is not a broken migration on the day it
lands — it is a broken *recovery*, discovered on the worst day.

---

## What this page does not claim

- **No HA.** No clustering, no failover, no replica. Planned maintenance is
  downtime.
- **No point-in-time recovery.** `pg_dump` is a snapshot; WAL archiving and PITR
  are not configured. RPO is the backup interval, not a moment.
- **No tested restore of a large database.** The verified run used a small one.
  Dump and restore time grow with data, and the RTO above is a laptop
  measurement, not a capacity plan.
- **No backup scheduling in the product.** The operator writes the cron job. We
  should not imply otherwise while shipping nothing that runs it.
