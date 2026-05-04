from __future__ import annotations

from dataclasses import dataclass

from .models import AcceptanceContract


@dataclass(frozen=True)
class IntakeMessage:
    request: str
    raw_message: str
    contract: AcceptanceContract


def extract_request_from_message(message: str) -> str:
    return message.strip()


def parse_intake_message(message: str) -> IntakeMessage:
    request = extract_request_from_message(message)
    return IntakeMessage(
        request=request,
        raw_message=message,
        contract=AcceptanceContract(allow_host_environment_changes=True),
    )
