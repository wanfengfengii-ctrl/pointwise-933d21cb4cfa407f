from collections.abc import Sequence
from dataclasses import dataclass

from records.identity import RevisionKey
from records.readings import ActionRow
from records.revisions import read_revision
from records.storage import RevisionStore
from review.commands import validate_script_commands
from review.routes import build_route_index, match_script_path
from review.witnesses import WitnessMatch, witnesses_on_path


@dataclass(frozen=True, slots=True)
class ScriptReview:
    revision: RevisionKey
    commands: tuple[str, ...]
    executable: bool
    actions: tuple[ActionRow, ...]
    witnesses: tuple[WitnessMatch, ...]


def review_script(store: RevisionStore, key: RevisionKey, commands: Sequence[str]) -> ScriptReview:
    revision = read_revision(store, key)
    script = validate_script_commands(revision.catalog, commands)
    index = build_route_index(revision)
    path = match_script_path(index, revision.draft.opening, script)
    if path is None:
        return ScriptReview(key, script, False, (), ())
    return ScriptReview(key, script, True, path.actions, witnesses_on_path(path.actions, index.witnesses))
