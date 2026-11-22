from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from records.identity import is_identifier


class UnknownCommand(ValueError):
    """The supplied command or command sequence is outside the catalog."""


@dataclass(frozen=True, slots=True)
class CommandCatalog:
    job: str
    commands: tuple[str, ...]

    def __post_init__(self):
        if not is_identifier(self.job):
            raise ValueError('a catalog requires a job identifier')
        if not isinstance(self.commands, Iterable) or isinstance(self.commands, (str, bytes, bytearray)):
            raise UnknownCommand('the catalog requires a collection of command identifiers')
        commands = tuple(self.commands)
        if not all(is_identifier(command) for command in commands):
            raise UnknownCommand('catalog commands must be nonempty identifiers')
        object.__setattr__(self, 'commands', tuple(sorted(set(commands))))

    def require_known(self, command: str) -> None:
        if not is_identifier(command) or command not in self.commands:
            raise UnknownCommand(f'unknown public command {command!r} for job {self.job}')


def validate_script_commands(catalog: CommandCatalog, commands: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(commands, Sequence) or isinstance(commands, (str, bytes, bytearray)):
        raise UnknownCommand('a script must be an ordered sequence of commands')
    script = tuple(commands)
    for command in script:
        catalog.require_known(command)
    return script
