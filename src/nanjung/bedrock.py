"""Bedrock 호출 래퍼. 일시 장애는 BedrockUnavailable로 감싼다."""
from __future__ import annotations

import json

from botocore.config import Config
from botocore.exceptions import ClientError, ConnectTimeoutError, EndpointConnectionError, ReadTimeoutError

REGION = "ap-northeast-2"
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
CHAT_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
TRANSIENT_CODES = {"ThrottlingException", "ServiceUnavailableException", "ModelNotReadyException",
                   "InternalServerException", "ModelTimeoutException"}

# 적재(배치): 넉넉한 대기와 재시도
INGEST_CONFIG = Config(read_timeout=60, connect_timeout=5, retries={"max_attempts": 3, "mode": "standard"})
# API: embed + converse가 직렬로 29초 안에 끝나도록 재시도 없이 짧게
API_CONFIG = Config(read_timeout=8, connect_timeout=2, retries={"total_max_attempts": 1, "mode": "standard"})

_clients: dict[str, object] = {}


class BedrockUnavailable(Exception):
    pass


def _make(profile: str):
    if profile not in _clients:
        import boto3
        cfg = API_CONFIG if profile == "api" else INGEST_CONFIG
        _clients[profile] = boto3.client("bedrock-runtime", region_name=REGION, config=cfg)
    return _clients[profile]


def api_client():
    return _make("api")


def _get_client(client):
    return client if client is not None else _make("ingest")


def _call(fn, *, post=None, **kw):
    """fn 호출과(post가 있으면) 응답 후처리까지 일시 장애를 BedrockUnavailable로 바꾼다."""
    try:
        resp = fn(**kw)
        return post(resp) if post else resp
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in TRANSIENT_CODES:
            raise BedrockUnavailable(str(e)) from e
        raise
    except (ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError) as e:
        raise BedrockUnavailable(str(e)) from e


def embed(text: str, client=None) -> list[float]:
    c = _get_client(client)
    body = json.dumps({"inputText": text, "dimensions": 1024, "normalize": True})
    return _call(c.invoke_model, modelId=EMBED_MODEL_ID, body=body,
                 contentType="application/json", accept="application/json",
                 post=lambda r: json.loads(r["body"].read())["embedding"])


def converse(system: str, messages: list[dict], max_tokens: int, temperature: float, client=None) -> str:
    c = _get_client(client)
    resp = _call(c.converse, modelId=CHAT_MODEL_ID, system=[{"text": system}], messages=messages,
                 inferenceConfig={"maxTokens": max_tokens, "temperature": temperature})
    return "".join(part.get("text", "") for part in resp["output"]["message"]["content"])
