"""Reusable string formats for component inputs (and their JSON schemas).

A :class:`Format` is ``Annotated`` metadata: drop it on a ``str`` field and the
field's JSON Schema carries a ``format`` keyword (so an LLM or a config author
knows what shape the string is) and, optionally, the value is validated. Only
the standard JSON Schema string formats ship here; define your own ``Format``
for anything domain-specific - there is no registry, so a custom format is just
a value you put in ``Annotated``::

    Sha256 = Annotated[str, Format("hash-sha256", "SHA-256 hex", _validate_sha256)]


    class LookupParams(BaseModel):
        host: Ipv4
        digest: Sha256

Formats compose with pydantic like any annotation, so they work with defaults,
``Field(...)`` and unions, and flow into a component's input schema unchanged.
"""

from collections.abc import Callable
from dataclasses import dataclass
import datetime
import ipaddress
import re
from typing import Annotated, Any
import urllib.parse
import uuid as uuid_module

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema


@dataclass(frozen=True, slots=True)
class Format:
    """``Annotated`` metadata: a JSON Schema ``format`` plus optional validation."""

    value: str
    description: str = ""
    validator: Callable[[str], None] | None = None

    def __get_pydantic_core_schema__(self, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        schema = handler(source_type)
        if self.validator is None:
            return schema
        return core_schema.no_info_after_validator_function(self._validate, schema)

    def _validate(self, value: str) -> str:
        assert self.validator is not None  # noqa: S101 - only wired when set
        try:
            self.validator(value)
        except ValueError as exc:
            raise ValueError(f"invalid {self.value}: {exc}") from exc
        return value

    def __get_pydantic_json_schema__(self, schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        json_schema = handler(schema)
        json_schema["format"] = self.value
        if self.description and not json_schema.get("description"):
            json_schema["description"] = self.description
        return json_schema


# --- standard validators (stdlib only) ---------------------------------------

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_JSON_POINTER_RE = re.compile(r"^(/([^/~]|~[01])*)*$")


def _validate_date(value: str) -> None:
    datetime.date.fromisoformat(value)


def _validate_time(value: str) -> None:
    datetime.time.fromisoformat(value)


def _validate_date_time(value: str) -> None:
    datetime.datetime.fromisoformat(value)


def _validate_ipv4(value: str) -> None:
    try:
        ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise ValueError(str(exc)) from exc


def _validate_ipv6(value: str) -> None:
    try:
        ipaddress.IPv6Address(value)
    except ipaddress.AddressValueError as exc:
        raise ValueError(str(exc)) from exc


def _validate_hostname(value: str) -> None:
    if not _HOSTNAME_RE.match(value):
        raise ValueError("expected an RFC 1123 hostname")


def _validate_email(value: str) -> None:
    if not _EMAIL_RE.match(value):
        raise ValueError("expected user@domain.tld")


def _validate_uri(value: str) -> None:
    parsed = urllib.parse.urlparse(value)
    if not parsed.scheme or re.search(r"\s", value):
        raise ValueError("expected an absolute URI with a scheme")


def _validate_uuid(value: str) -> None:
    try:
        uuid_module.UUID(value)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


def _validate_regex(value: str) -> None:
    try:
        re.compile(value)
    except re.error as exc:
        raise ValueError(str(exc)) from exc


def _validate_json_pointer(value: str) -> None:
    if not _JSON_POINTER_RE.match(value):
        raise ValueError("expected an RFC 6901 JSON Pointer")


# --- standard string formats -------------------------------------------------

Date = Annotated[str, Format("date", "Date, ISO 8601 (YYYY-MM-DD).", _validate_date)]
Time = Annotated[str, Format("time", "Time, ISO 8601 (HH:MM:SS).", _validate_time)]
DateTime = Annotated[str, Format("date-time", "Date-time, ISO 8601.", _validate_date_time)]
Email = Annotated[str, Format("email", "Email address (user@domain).", _validate_email)]
Hostname = Annotated[str, Format("hostname", "Hostname (RFC 1123).", _validate_hostname)]
Ipv4 = Annotated[str, Format("ipv4", "IPv4 address.", _validate_ipv4)]
Ipv6 = Annotated[str, Format("ipv6", "IPv6 address.", _validate_ipv6)]
Uri = Annotated[str, Format("uri", "Absolute URI with a scheme.", _validate_uri)]
Uuid = Annotated[str, Format("uuid", "UUID (8-4-4-4-12 hex).", _validate_uuid)]
Regex = Annotated[str, Format("regex", "Regular expression pattern.", _validate_regex)]
JsonPointer = Annotated[str, Format("json-pointer", "JSON Pointer (RFC 6901).", _validate_json_pointer)]

__all__ = [
    "Date",
    "DateTime",
    "Email",
    "Format",
    "Hostname",
    "Ipv4",
    "Ipv6",
    "JsonPointer",
    "Regex",
    "Time",
    "Uri",
    "Uuid",
]
