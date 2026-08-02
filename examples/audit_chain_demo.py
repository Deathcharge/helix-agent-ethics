"""Write and verify a temporary keyed, metadata-only policy audit chain."""

from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory

from samsarix_ethics import (
    HmacAuditChainSink,
    ToolCallDeniedError,
    ToolGate,
    generate_audit_chain_key,
    load_policy,
    verify_audit_chain,
)


def main() -> None:
    root = Path(__file__).parent
    key = generate_audit_chain_key()
    with TemporaryDirectory(prefix="samsarix-audit-chain-") as directory:
        chain_path = Path(directory) / "decisions.jsonl"
        sink = HmacAuditChainSink(
            chain_path,
            key,
            stream_id="support-agent-demo",
        )
        gate = ToolGate(
            load_policy(root / "policies/tool-call-baseline.json"),
            audit_sink=sink,
        )

        read_ticket = gate.bind("read_ticket", capabilities=["resource:read"])
        read_ticket.execute(
            {"ticket_id": "T-100"},
            lambda arguments: {"ticket_id": arguments["ticket_id"], "status": "open"},
            actor={"id": "support-agent"},
        )

        delete_ticket = gate.bind("delete_ticket", capabilities=["destructive"])
        with suppress(ToolCallDeniedError):
            delete_ticket.execute(
                {"ticket_id": "T-100"},
                lambda _arguments: print("this callback must not run"),
                actor={"id": "support-agent"},
            )

        head_mac = sink.head_mac
        if head_mac is None:
            raise RuntimeError("the demo did not write an audit-chain entry")
        verification = verify_audit_chain(
            chain_path,
            key,
            expected_head=head_mac,
            expected_stream_id="support-agent-demo",
        )
        print(json.dumps(verification.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
