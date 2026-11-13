"""Post-call audit: every number the agent spoke must appear in a tool result or in the user's words."""
from __future__ import annotations

from typing import Any

from voice.audit import audit_transcript


def test_numbers_backed_by_tool_results_pass() -> None:
    transcript: list[dict[str, Any]] = [
        {"role": "agent", "message": "Sono un assistente di intelligenza artificiale."},
        {"role": "user", "message": "What is near via Nazionale 12?"},
        {"role": "agent", "tool_results": [{"tool_name": "ask_twin", "result_value": "{\"speak\": \"2 schools within 300 m, field 1,8 to 3.4 V/m\"}"}]},
        {"role": "agent", "message": "There are 2 schools within 300 metres of number 12. The field is 1.8 to 3,4 volts per metre."},
    ]
    assert audit_transcript(transcript) == []


def test_invented_number_is_flagged() -> None:
    transcript: list[dict[str, Any]] = [
        {"role": "agent", "tool_results": [{"result_value": "{\"speak\": \"2 schools\"}"}]},
        {"role": "agent", "message": "There are 2 schools and 5 hospitals."},
    ]
    findings = audit_transcript(transcript)
    assert [f.number for f in findings] == ["5"]
    assert findings[0].turn == 1
