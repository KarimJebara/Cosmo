"""Bank-CSV importer registry."""

from cosmo.importers.base import BaseImporter, ImportRecord
from cosmo.importers.generic import GenericCsvImporter, GenericMapping
from cosmo.importers.n26 import N26Importer
from cosmo.importers.revolut import RevolutImporter
from cosmo.importers.wise import WiseImporter

# Map of importer kind → instance. Adding a bank is a one-liner here.
IMPORTERS: dict[str, BaseImporter] = {
    "revolut": RevolutImporter(),
    "wise": WiseImporter(),
    "n26": N26Importer(),
    "generic": GenericCsvImporter(),
}


def get_importer(kind: str) -> BaseImporter:
    if kind not in IMPORTERS:
        raise ValueError(
            f"Unknown importer kind {kind!r}. "
            f"Known kinds: {sorted(IMPORTERS)}"
        )
    return IMPORTERS[kind]


__all__ = [
    "IMPORTERS",
    "BaseImporter",
    "GenericCsvImporter",
    "GenericMapping",
    "ImportRecord",
    "N26Importer",
    "RevolutImporter",
    "WiseImporter",
    "get_importer",
]
