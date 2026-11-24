"""글꼴 1회 수집: Pretendard subset 3개 + Noto Serif KR(unicode-range 분할) → web/fonts/

다시 실행해도 결과가 같다(이미 있는 파일은 다시 받지 않는다). 결과물은 커밋하고 배포 때 다시 받지 않는다.
사용: python scripts/fetch_fonts.py
"""
from __future__ import annotations

import io
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "web" / "fonts"
PRETENDARD_VERSION = "1.3.9"
PRETENDARD_ZIP = (f"https://github.com/orioncactus/pretendard/releases/download/v{PRETENDARD_VERSION}/"
                  f"Pretendard-{PRETENDARD_VERSION}.zip")
PRETENDARD_IN_ZIP = "web/static/woff2-subset/Pretendard-{name}.subset.woff2"
PRETENDARD_WEIGHTS = {"Regular": 400, "Medium": 500, "SemiBold": 600}
NOTO_CSS = "https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;700&display=swap"
CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/142.0.0.0 Safari/537.36")

BLOCK_RE = re.compile(r"@font-face\s*\{(.*?)\}", re.S)
URL_RE = re.compile(r"url\((https://[^)]+\.woff2)\)")
WEIGHT_RE = re.compile(r"font-weight:\s*(\d+)")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": CHROME_UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def pretendard() -> str:
    out_dir = FONTS / "pretendard"
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = {n: out_dir / f"Pretendard-{n}.subset.woff2" for n in PRETENDARD_WEIGHTS}
    missing = [n for n, p in targets.items() if not p.exists()]
    if missing:
        with zipfile.ZipFile(io.BytesIO(_get(PRETENDARD_ZIP))) as z:
            names = z.namelist()
            for n in missing:
                want = PRETENDARD_IN_ZIP.format(name=n)
                found = want if want in names else next(
                    (x for x in names if x.endswith(f"/Pretendard-{n}.subset.woff2")), None)
                if found is None:
                    raise SystemExit(f"릴리스 zip에 Pretendard-{n}.subset.woff2 없음")
                if found != want:
                    print(f"주의: 경로가 다름 {found}")
                targets[n].write_bytes(z.read(found))
    return "".join(
        "@font-face {\n"
        "  font-family: 'Pretendard';\n"
        "  font-style: normal;\n"
        f"  font-weight: {w};\n"
        "  font-display: swap;\n"
        f"  src: url('pretendard/Pretendard-{n}.subset.woff2') format('woff2');\n"
        "}\n"
        for n, w in PRETENDARD_WEIGHTS.items())


UNICODE_RE = re.compile(r"unicode-range:\s*([^;]+);")


def noto_css(css: str, out_dir: Path, fetch=_get) -> str:
    """Google Fonts CSS → 조각 파일을 내용 해시 이름으로 한 번만 저장하고 @font-face를 만든다.

    Google은 가변 글꼴이라 400·700에 같은 파일을 준다. 같은 파일+같은 unicode-range면 규칙 하나에
    font-weight: 400 700 범위로 선언해 브라우저가 한 번만 받게 한다. 이름이 내용 해시라
    업스트림 순서가 바뀌어도 결과가 같다.
    """
    import hashlib

    out_dir.mkdir(parents=True, exist_ok=True)
    groups: dict[tuple[str, str], set[int]] = {}
    for body in BLOCK_RE.findall(css):
        url, weight, urange = URL_RE.search(body), WEIGHT_RE.search(body), UNICODE_RE.search(body)
        if not url or not weight or not urange:
            raise SystemExit("예상과 다른 Google Fonts CSS 형식")
        data = fetch(url.group(1))
        name = hashlib.sha256(data).hexdigest()[:16] + ".woff2"
        path = out_dir / name
        if not path.exists():
            path.write_bytes(data)
        groups.setdefault((name, urange.group(1).strip()), set()).add(int(weight.group(1)))
    rules = []
    for (name, urange), weights in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        w = " ".join(str(x) for x in (sorted(weights) if len(weights) == 1 else (min(weights), max(weights))))
        rules.append("".join(line + "\n" for line in (
            "@font-face {",
            "  font-family: 'Noto Serif KR';",
            "  font-style: normal;",
            f"  font-weight: {w};",
            "  font-display: swap;",
            f"  src: url('noto-serif-kr/{name}') format('woff2');",
            f"  unicode-range: {urange};",
            "}")))
    return "".join(rules)


def noto() -> str:
    out_dir = FONTS / "noto-serif-kr"
    css = noto_css(_get(NOTO_CSS).decode("utf-8"), out_dir)
    used = set(re.findall(r"noto-serif-kr/([0-9a-f]{16}\.woff2)", css))
    for old in out_dir.glob("*.woff2"):  # 이전 이름(굵기-순번)이나 더 이상 쓰지 않는 조각은 지운다
        if old.name not in used:
            old.unlink()
    return css


def main() -> None:
    css = "/* 자동 생성: python scripts/fetch_fonts.py — 손으로 고치지 않는다 */\n" + pretendard() + noto()
    (FONTS / "fonts.css").write_text(css, encoding="utf-8", newline="\n")
    n_noto = len(list((FONTS / "noto-serif-kr").glob("*.woff2")))
    print(f"Pretendard 3, Noto Serif KR woff2 {n_noto}, @font-face {css.count('@font-face')}")


if __name__ == "__main__":
    sys.exit(main())
