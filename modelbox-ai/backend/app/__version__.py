"""Canonical product version — the single source of truth.

Every other version stamp in the repository is checked against this value by
``scripts/check_versions.py``, which runs as a CI job. Before Sprint 1 the four
stamps disagreed four ways (``package.json`` 1.2.0, ``/health`` 1.2.0, compose
image tags v1.3.0, release notes v1.5.0), so an operator running a v1.5.0
appliance was told they were on 1.2.0.

It lives inside ``backend/`` deliberately: ``docker/Dockerfile.backend`` builds
with ``../backend`` as its context, so a repository-root VERSION file would not
be present at image build time.

Bump here, then run ``python scripts/check_versions.py --fix`` to propagate.
"""

from __future__ import annotations

__version__ = "1.9.0"
