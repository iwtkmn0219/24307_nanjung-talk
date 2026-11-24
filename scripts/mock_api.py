"""로컬 목 API (포트 8787). 실제 계약(src/nanjung/handlers/{chat,diary}.py)과 같은 JSON을 돌려준다.

사용: python scripts/mock_api.py  → web/config.js의 API_BASE를 "http://localhost:8787"로(커밋하지 않는다)
GET /diary?scenario=nearest|grief|fail, POST /chat 키워드: 아들·인공지능·한도·장애·태그
"""
from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 8787
ORIGIN = "http://localhost:5500"
DELAY_S = 1.5
NOTE = "원문: 『이충무공전서』 난중일기 / 번역: AI"


def card(i: int, label: str, orig: str, tr: str) -> dict:
    return {"id": f"mock-{i}", "label": label, "original_line": orig, "translation_line": tr, "note": NOTE}


CARDS = [
    card(1, "계사년(1593) 2월 22일", "二十二日。風勢不順。", "바람이 순하지 않았다."),
    card(2, "갑오년(1594) 3월 6일", "初六日。大風。", "큰바람이 불었다."),
    card(3, "임진년(1592) 4월 13일", "十三日壬寅。", "13일 임인. 맑음."),
]
SUGGESTIONS = ["거북선은 어찌 만드셨소?", "명량에서 두렵진 않으셨소?", "한산도의 밤은 어땠소?"]


def diary(scenario: str | None) -> tuple[int, dict]:
    if scenario == "fail":
        return 500, {"message": "Internal Server Error"}
    if scenario == "nearest":
        entry = {"id": "1594-02-29", "label": "갑오년(1594) 2월 29일", "solar_date": "1594-03-20",
                 "original": "二十九日戊申。晴。", "translation": "29일 무신. 맑음.", "emotion": "일상",
                 "intro": "맑은 날이었소."}
        return 200, {"entry": entry, "questions": SUGGESTIONS, "exact": False, "source_note": NOTE}
    entry = {"id": "1597-09-16", "label": "정유년(1597) 9월 16일", "solar_date": "1597-10-26",
             "original": "十六日甲辰。晴。早朝別望進告。賊船不知其數。直向我船云。",
             "translation": "16일 갑진. 맑음. 이른 아침에 별망군이 와서 보고하기를, 적선이 수를 헤아릴 수 없이 우리 배를 향해 곧바로 온다고 했다.",
             "emotion": "비통" if scenario == "grief" else "일상",
             "intro": "명량의 바다에서 싸운 날이었소."}
    return 200, {"entry": entry, "questions": ["그날 두렵지 않으셨소?", "배는 몇 척이었소?", "물살은 어땠소?"],
                 "exact": True, "source_note": NOTE}


def chat(message: str) -> tuple[int, dict]:
    if "한도" in message:
        return 429, {"answer": "오늘은 그만 쉬어야겠소. 내일 다시 오시오."}
    if "장애" in message:
        return 503, {"answer": "잠시 숨을 고르겠소. 조금 뒤 다시 물어 주시오."}
    if "인공지능" in message:
        return 200, {"answer": "처음 듣는 말이라 내 답할 길이 없소. 대신 내 일기 이야기를 들려주리다.",
                     "mode": "out_of_scope", "sources": [], "suggestions": SUGGESTIONS}
    if "아들" in message:
        return 200, {"answer": "면이 죽었다는 기별을 받던 날, 하늘이 어찌 이리 어질지 못한가 하였소.",
                     "mode": "serious",
                     "sources": [card(9, "정유년(1597) 10월 14일", "十四日辛未。", "14일 신미.")],
                     "suggestions": SUGGESTIONS}
    if "태그" in message:
        return 200, {"answer": "<img src=x onerror=alert(1)>는 모르오", "mode": "normal",
                     "sources": [card(7, "<b>굵게</b>", "<script>alert(2)</script>", "<i>기울임</i>")],
                     "suggestions": SUGGESTIONS}
    return 200, {"answer": "바람이 사나운 날엔 나도 속이 편치 않았소. 그래도 배를 띄워야 할 날은 띄웠다오.",
                 "mode": "normal", "sources": CARDS, "suggestions": SUGGESTIONS}


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type, x-client-id")

    def _send(self, status: int, body: dict):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        if u.path != "/diary":
            return self._send(404, {"error": "없는 경로"})
        time.sleep(DELAY_S)
        self._send(*diary(parse_qs(u.query).get("scenario", [None])[0]))

    def do_POST(self):
        if urlparse(self.path).path != "/chat":
            return self._send(404, {"error": "없는 경로"})
        if not self.headers.get("x-client-id"):
            return self._send(400, {"error": "X-Client-Id 없음"})
        n = int(self.headers.get("content-length") or 0)
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            message = data["message"]
        except (ValueError, KeyError, TypeError):
            return self._send(400, {"error": "본문 오류"})
        time.sleep(DELAY_S)
        self._send(*chat(message))


if __name__ == "__main__":
    print(f"mock api http://localhost:{PORT} (origin {ORIGIN})", file=sys.stderr)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
