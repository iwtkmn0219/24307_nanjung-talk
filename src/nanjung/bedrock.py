"""Bedrock 호출 래퍼. 일시 장애는 BedrockUnavailable로 감싼다."""
from __future__ import annotations

import json

from botocore.exceptions import ClientError, ConnectTimeoutError, EndpointConnectionError, ReadTimeoutError

REGION = "ap-northeast-2"
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
CHAT_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
TRANSIENT_CODES = {"ThrottlingException", "ServiceUnavailableException", "ModelNotReadyException",
                   "InternalServerException"}

_client = None


class BedrockUnavailable(Exception):
    pass


def _get_client(client):
    global _client
    if client is not None:
        return client
    if _client is None:
        import boto3
        from botocore.config import Config
        _client = boto3.client("bedrock-runtime", region_name=REGION,
                               config=Config(read_timeout=20, connect_timeout=5,
                                             retries={"max_attempts": 2, "mode": "standard"}))
    return _client


def _call(fn, **kw):
    try:
        return fn(**kw)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in TRANSIENT_CODES:
            raise BedrockUnavailable(str(e)) from e
        raise
    except (ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError) as e:
        raise BedrockUnavailable(str(e)) from e


def embed(text: str, client=None) -> list[float]:
    c = _get_client(client)
    body = json.dumps({"inputText": text, "dimensions": 1024, "normalize": True})
    resp = _call(c.invoke_model, modelId=EMBED_MODEL_ID, body=body,
                 contentType="application/json", accept="application/json")
    return json.loads(resp["body"].read())["embedding"]


def converse(system: str, messages: list[dict], max_tokens: int, temperature: float, client=None) -> str:
    c = _get_client(client)
    resp = _call(c.converse, modelId=CHAT_MODEL_ID, system=[{"text": system}], messages=messages,
                 inferenceConfig={"maxTokens": max_tokens, "temperature": temperature})
    return "".join(part.get("text", "") for part in resp["output"]["message"]["content"])
