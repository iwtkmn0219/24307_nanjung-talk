from datetime import datetime, timedelta, timezone

import boto3
import pytest
from moto import mock_aws

from nanjung.quota import KST, allow


@pytest.fixture
def table(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="ap-northeast-2")
        t = ddb.create_table(TableName="Usage", BillingMode="PAY_PER_REQUEST",
                             KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
                             AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}])
        yield t


def test_kst_is_utc_plus_9():
    assert KST.utcoffset(None) == timedelta(hours=9)


def test_20th_allowed_21st_denied(table):
    t = datetime(2026, 12, 1, 23, 0, tzinfo=KST)
    assert all(allow(table, "c1", t, 20) for _ in range(20)) and allow(table, "c1", t, 20) is False
    assert table.get_item(Key={"pk": "c1#2026-12-01"})["Item"]["cnt"] == 20


def test_resets_after_kst_midnight(table):
    late = datetime(2026, 12, 1, 23, 59, tzinfo=KST)
    for _ in range(20):
        allow(table, "c1", late, 20)
    assert allow(table, "c1", late, 20) is False
    assert allow(table, "c1", datetime(2026, 12, 2, 0, 0, tzinfo=KST), 20) is True


def test_utc_time_is_bucketed_by_kst_day(table):
    # UTC 2026-12-01 15:30 = KST 2026-12-02 00:30
    allow(table, "c1", datetime(2026, 12, 1, 15, 30, tzinfo=timezone.utc), 20)
    assert "Item" in table.get_item(Key={"pk": "c1#2026-12-02"})


def test_clients_are_independent(table):
    t = datetime(2026, 12, 1, 12, 0, tzinfo=KST)
    for _ in range(20):
        allow(table, "c1", t, 20)
    assert allow(table, "c1", t, 20) is False
    assert allow(table, "c2", t, 20) is True


def test_expires_at_is_day_after_next_kst_midnight(table):
    allow(table, "c1", datetime(2026, 12, 1, 9, 0, tzinfo=KST), 20)
    item = table.get_item(Key={"pk": "c1#2026-12-01"})["Item"]
    assert int(item["expires_at"]) == int(datetime(2026, 12, 3, 0, 0, tzinfo=KST).timestamp())
