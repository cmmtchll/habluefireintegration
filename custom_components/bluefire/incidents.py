"""Bounded, entry-local incident evidence; never a continuous packet log."""

import asyncio
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging

_LOGGER = logging.getLogger(__name__)
INCIDENT_LIMIT = 10
INCIDENT_BYTES = 512 * 1024
BEFORE_LIMIT = 32
AFTER_LIMIT = 8
SAVE_DELAY = 1


class IncidentJournal:
    """Freeze pre/post-event metadata and delegate writes to HA storage."""

    def __init__(self, store, *, raw_enabled=False):
        self.store = store
        self.raw_enabled = raw_enabled
        self._records = []
        self._recent = deque(maxlen=BEFORE_LIMIT)
        self._active = None
        self._dirty = False
        self._dropped = 0
        self._removed = False
        self._revision = 0
        self._lock = asyncio.Lock()
        self._save_scheduled = False

    async def async_load(self):
        data = await self.store.async_load()
        if data is not None:
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("incidents"), list)
                or type(data.get("dropped_oversized", 0)) is not int
                or data.get("dropped_oversized", 0) < 0
                or any(
                    not isinstance(item, dict)
                    or not isinstance(item.get("context"), dict)
                    or not isinstance(item.get("triggers"), list)
                    or any(not isinstance(kind, str)
                           for kind in item["triggers"])
                    or any(
                        not isinstance(item.get(window), list)
                        or len(item[window]) > limit
                        or any(not isinstance(note, dict)
                               for note in item[window])
                        for window, limit in (
                            ("before", BEFORE_LIMIT), ("after", AFTER_LIMIT),
                        )
                    )
                    for item in data["incidents"]
                )
            ):
                raise ValueError("Invalid BlueFire incident journal")
            self._records = deepcopy(data["incidents"])
            self._dropped = data.get("dropped_oversized", 0)
        if not self.raw_enabled:
            for record in self._records:
                for note in record.get("before", []) + record.get("after", []):
                    if note.pop("raw_reports", None) is not None:
                        self._dirty = True
        self._trim()
        if self._dirty:
            await self.async_flush()

    def new_session(self):
        """Do not join evidence from distinct BLE connections."""
        self._recent.clear()
        self._active = None

    def observe(self, notification):
        if self._removed:
            return
        note = deepcopy(notification)
        if not self.raw_enabled:
            note.pop("raw_reports", None)
        self._recent.append(note)
        if self._active is not None:
            self._active["after"].append(deepcopy(note))
            if len(self._active["after"]) >= AFTER_LIMIT:
                self._active = None
            self._changed()

    def record(self, kind, context):
        """Coalesce a burst into one incident until its post-window is full."""
        if self._removed:
            return
        if self._active is not None:
            if kind not in self._active["triggers"]:
                self._active["triggers"].append(kind)
            self._active["latest_context"] = deepcopy(context)
        else:
            self._active = {
                "time": datetime.now(timezone.utc).isoformat(),
                "triggers": [kind],
                "context": deepcopy(context),
                "before": deepcopy(list(self._recent)),
                "after": [],
            }
            self._records.append(self._active)
        self._changed()

    def _trim(self, *, measure_size=True):
        while len(self._records) > INCIDENT_LIMIT:
            self._records.pop(0)
            self._dirty = True
        if not measure_size:
            return
        while self._records and len(json.dumps(
            {
                "incidents": self._records, "dropped_oversized": self._dropped,
            }, ensure_ascii=True,
        ).encode("utf-8")) > INCIDENT_BYTES:
            removed = self._records.pop(0)
            if removed is self._active:
                self._active = None
            self._dropped += 1
            self._dirty = True
            _LOGGER.warning("BlueFire incident journal size limit reached")

    def finish_session(self, context):
        if (
            not self._removed and self._records
            and self._records[-1]["context"].get("attempt")
            == context.get("attempt")
        ):
            self._records[-1]["final_context"] = deepcopy(context)
            self._records[-1]["completed_at"] = (
                datetime.now(timezone.utc).isoformat()
            )
            self._active = None
            self._changed()

    def _changed(self):
        self._revision += 1
        self._dirty = True
        self._trim(measure_size=False)
        if not self._save_scheduled:
            self._save_scheduled = True
            self.store.async_delay_save(self._delayed_data, SAVE_DELAY)

    def _delayed_data(self):
        self._save_scheduled = False
        return self._data()

    def _data(self):
        self._trim()
        return {
            "incidents": deepcopy(self._records),
            "dropped_oversized": self._dropped,
        }

    def diagnostics(self):
        return {
            "raw_enabled": self.raw_enabled,
            "raw_policy": "checksum-valid telemetry only; no startup/controls",
            "incident_limit": INCIDENT_LIMIT,
            "byte_limit": INCIDENT_BYTES,
            "before_limit": BEFORE_LIMIT,
            "after_limit": AFTER_LIMIT,
            "dropped_oversized": self._dropped,
            **self._data(),
        }

    async def async_flush(self):
        async with self._lock:
            while self._dirty and not self._removed:
                revision = self._revision
                self._save_scheduled = False
                await self.store.async_save(self._data())
                self._dirty = self._revision != revision

    async def async_remove(self):
        self._removed = True
        async with self._lock:
            await self.store.async_remove()
            self._records.clear()
            self.new_session()
            self._dirty = False
            self._save_scheduled = False


def incident_store(hass, entry_id):
    """Use the entry identity, not its mutable MAC or vehicle name."""
    from homeassistant.helpers.storage import Store

    return Store(
        hass, 1, f"bluefire.incidents.{entry_id}",
        private=True, atomic_writes=True,
    )
