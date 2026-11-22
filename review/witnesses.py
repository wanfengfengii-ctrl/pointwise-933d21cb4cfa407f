from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from records.readings import ActionRow, WitnessRow
from records.revisions import Revision


@dataclass(frozen=True, slots=True)
class WitnessMatch:
    action_id: str
    witness: WitnessRow


def index_qualified_witnesses(revision: Revision) -> dict[str, tuple[WitnessRow, ...]]:
    """The accepted witness table already contains only qualified rows."""
    grouped = defaultdict(list)
    for witness in sorted(revision.draft.witnesses, key=lambda row: row.row_id):
        grouped[witness.action_id].append(witness)
    return {action_id: tuple(rows) for action_id, rows in grouped.items()}


def witnesses_on_path(
    actions: Iterable[ActionRow], index: Mapping[str, tuple[WitnessRow, ...]]
) -> tuple[WitnessMatch, ...]:
    return tuple(
        WitnessMatch(action.row_id, witness)
        for action in actions
        for witness in index.get(action.row_id, ())
    )
