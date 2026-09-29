"""Host integration layer: discover and register the host's user-defined functions.

See design doc 02 §6.10.

**Why a separate layer**: entry point discovery reads distribution metadata (IO), while the
``core`` invariant is "no IO". The IO is collected here so ``core.udfs`` stays pure dictionary
operations.

A host can hook in two equivalent ways:

```python
import uniparser2
uniparser2.register_udf("clean_title", my_clean_title)      # explicit registration
```

```toml
# the host package's pyproject.toml
[project.entry-points."uniparser2.udfs"]
clean_title = "my_pkg.udfs:clean_title"
```
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Any

from .core.udfs import register_udf

logger = logging.getLogger("uniparser2")

UDF_ENTRY_POINT_GROUP = "uniparser2.udfs"


def load_entry_point_udfs(group: str = UDF_ENTRY_POINT_GROUP) -> tuple[str, ...]:
    """Scan the entry points and register them; return the names registered this time.

    A single entry that fails to load is only logged as a WARNING and skipped: a chain that
    references it reports ``UP2-E1010`` at compile time, which is signal enough, while letting one
    bad entry abort the whole ``import uniparser2`` would cost too much.
    """
    loaded: list[str] = []
    for entry in entry_points(group=group):
        try:
            target: Any = entry.load()
        except Exception as exc:
            logger.warning(
                "user-defined function entry point %s failed to load: %r", entry.name, exc
            )
            continue
        register_udf(entry.name, target)
        loaded.append(entry.name)
    if loaded:
        logger.debug(
            "user-defined functions registered from entry points: %s", ", ".join(sorted(loaded))
        )
    return tuple(sorted(loaded))
