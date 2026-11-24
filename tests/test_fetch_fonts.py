import hashlib

from fetch_fonts import noto_css

CSS = """/* [0] */
@font-face {
  font-family: 'Noto Serif KR';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url(https://fonts.gstatic.com/s/a.woff2) format('woff2');
  unicode-range: U+1-2;
}
/* [1] */
@font-face {
  font-family: 'Noto Serif KR';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url(https://fonts.gstatic.com/s/b.woff2) format('woff2');
  unicode-range: U+3-4;
}
/* [0] */
@font-face {
  font-family: 'Noto Serif KR';
  font-style: normal;
  font-weight: 700;
  font-display: swap;
  src: url(https://fonts.gstatic.com/s/a.woff2) format('woff2');
  unicode-range: U+1-2;
}
/* [1] */
@font-face {
  font-family: 'Noto Serif KR';
  font-style: normal;
  font-weight: 700;
  font-display: swap;
  src: url(https://fonts.gstatic.com/s/b.woff2) format('woff2');
  unicode-range: U+3-4;
}
"""
DATA = {"https://fonts.gstatic.com/s/a.woff2": b"AAAA", "https://fonts.gstatic.com/s/b.woff2": b"BBBB"}


def name(b):
    return hashlib.sha256(b).hexdigest()[:16] + ".woff2"


def test_same_file_for_both_weights_becomes_one_rule_and_one_file(tmp_path):
    css = noto_css(CSS, tmp_path, DATA.__getitem__)
    files = sorted(p.name for p in tmp_path.glob("*.woff2"))
    assert files == sorted([name(b"AAAA"), name(b"BBBB")])
    assert css.count("@font-face") == 2
    assert css.count("font-weight: 400 700;") == 2
    assert f"url('noto-serif-kr/{name(b'AAAA')}')" in css and "U+1-2" in css
    assert "https://" not in css and "font-display: swap" in css


def test_result_does_not_depend_on_upstream_order(tmp_path):
    blocks = CSS.split("/* [")
    reordered = "/* [".join([blocks[0]] + list(reversed(blocks[1:])))
    a = noto_css(CSS, tmp_path / "a", DATA.__getitem__)
    b = noto_css(reordered, tmp_path / "b", DATA.__getitem__)
    assert a == b


def test_different_files_per_weight_stay_separate(tmp_path):
    data = {**DATA, "https://fonts.gstatic.com/s/c.woff2": b"CCCC"}
    css_in = CSS.replace("s/a.woff2", "s/c.woff2", 1)  # 400의 첫 조각만 다른 파일
    css = noto_css(css_in, tmp_path, data.__getitem__)
    assert css.count("@font-face") == 3
    assert "font-weight: 400;" in css and "font-weight: 700;" in css and "font-weight: 400 700;" in css
