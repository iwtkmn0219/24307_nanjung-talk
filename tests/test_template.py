from pathlib import Path

from cfnlint.decode import decode_str

TEMPLATE, _ = decode_str(Path("template.yaml").read_text(encoding="utf-8"))
RES = TEMPLATE["Resources"]


def test_no_function_reserves_concurrency_by_default():
    # 신규 계정(동시성 한도 10)에서는 어떤 예약도 배포를 막는다
    for name, r in RES.items():
        if r["Type"] == "AWS::Serverless::Function":
            rce = r["Properties"].get("ReservedConcurrentExecutions")
            assert not isinstance(rce, int), name
    assert TEMPLATE["Parameters"]["IngestReservedConcurrency"]["Default"] == 0
