from dataclasses import dataclass


class RevisionRejected(ValueError):
    """The candidate cannot become a fixed revision."""


class RevisionMissing(LookupError):
    """The precise revision key was not found."""


MAX_SQLITE_NUMBER = (1 << 63) - 1


def is_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value) and not any(
        '\ud800' <= char <= '\udfff' for char in value
    )


def is_record_number(value: object) -> bool:
    return type(value) is int and 0 < value <= MAX_SQLITE_NUMBER


@dataclass(frozen=True, slots=True)
class StationKey:
    job: str
    station: str

    def __post_init__(self):
        if not is_identifier(self.job) or not is_identifier(self.station):
            raise RevisionRejected('job and station must be nonempty identifiers')


@dataclass(frozen=True, slots=True)
class RevisionKey:
    station: StationKey
    number: int

    def __post_init__(self):
        if not isinstance(self.station, StationKey) or not is_record_number(self.number):
            raise RevisionRejected('invalid revision key')
