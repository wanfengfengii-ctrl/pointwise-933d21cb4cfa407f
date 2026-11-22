from collections.abc import Sequence
from dataclasses import dataclass

from records.identity import RevisionRejected, is_identifier


@dataclass(frozen=True, slots=True)
class ActionRow:
    row_id: str
    source: str
    target: str
    kind: str
    label: str
    reading: str = ''


@dataclass(frozen=True, slots=True)
class WitnessRow:
    row_id: str
    action_id: str
    note: str = ''


@dataclass(frozen=True, slots=True)
class RevisionDraft:
    opening: str
    actions: tuple[ActionRow, ...]
    witnesses: tuple[WitnessRow, ...] = ()


def validate_readings(draft: RevisionDraft) -> RevisionDraft:
    if not isinstance(draft, RevisionDraft) or not is_identifier(draft.opening):
        raise RevisionRejected('a valid opening state is required')
    if not isinstance(draft.actions, Sequence) or not isinstance(draft.witnesses, Sequence):
        raise RevisionRejected('actions and witnesses must be sequences of rows')
    if isinstance(draft.actions, (str, bytes, bytearray)) or isinstance(
        draft.witnesses, (str, bytes, bytearray)
    ):
        raise RevisionRejected('actions and witnesses must be sequences of rows')
    actions = tuple(draft.actions)
    witnesses = tuple(draft.witnesses)
    action_ids = set()
    for row in actions:
        if not isinstance(row, ActionRow):
            raise RevisionRejected('invalid action row')
        if not all(is_identifier(item) for item in (row.row_id, row.source, row.target, row.label)):
            raise RevisionRejected('action requires an identifier, endpoints and label')
        if row.kind not in ('local', 'public') or not isinstance(row.reading, str):
            raise RevisionRejected(f'invalid action representation: {row.row_id}')
        if row.row_id in action_ids:
            raise RevisionRejected(f'duplicate action row: {row.row_id}')
        action_ids.add(row.row_id)
    witness_ids = set()
    for row in witnesses:
        if not isinstance(row, WitnessRow) or not all(
            is_identifier(item) for item in (row.row_id, row.action_id)
        ) or not isinstance(row.note, str):
            raise RevisionRejected('invalid witness row')
        if row.row_id in witness_ids:
            raise RevisionRejected(f'duplicate witness row: {row.row_id}')
        if row.action_id not in action_ids:
            raise RevisionRejected(f'witness {row.row_id} references absent action {row.action_id}')
        witness_ids.add(row.row_id)
    return RevisionDraft(draft.opening, actions, witnesses)
