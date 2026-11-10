#!/usr/bin/env python3
"""Build a Hunspell dictionary from a text corpus -- no hand-typing.

Pipeline: corpus -> tokens (tokenized the same way craft-proof's `words()` does)
-> normalized -> frequency-counted -> filtered -> `spelling.dic` + `spelling.aff`
+ check words + a coverage report.

Why "the same way craft-proof does" matters: a dictionary is only as good as its
agreement with the tokenizer that queries it. `craft_proof::words()`
(crates/proof/src/lib.rs:795) treats a character as part of a word when it is
alphanumeric, a combining mark, or one of ' ’ -, and trims leading/trailing
' ’ - from each token. Anything else -- ZWNJ (U+200C), tatweel-free spaces,
punctuation -- splits. So ZWNJ splits Sorani words into parts, and the parts are
what must be in the dictionary.

Usage:
    # 1. collect a corpus (Wikipedia plain text, one file per batch)
    python build_dic.py fetch --lang ckb --articles 2000 --out corpus/ckb

    # 2. build the dictionary
    python build_dic.py build --lang ckb --corpus corpus/ckb --out ckb \\
        --min-freq 3 --holdout 0.1

Outputs: ckb/spelling.aff, ckb/spelling.dic, ckb/checks.toml, ckb/report.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

# Characters craft-proof's tokenizer keeps inside a word (besides letters/numbers/marks).
WORD_PUNCT = {"'", "\u2019", "-"}
TRIM = "'\u2019-"
# Arabic-script joiners and marks that must not affect a dictionary lookup.
TATWEEL = "\u0640"
HARAKAT = set("\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652\u0653\u0654\u0655\u0670"
              "\u06d6\u06d7\u06d8\u06d9\u06da\u06db\u06dc\u06df\u06e0\u06e1\u06e2\u06e3"
              "\u06e4\u06e7\u06e8\u06ea\u06eb\u06ec\u06ed")


def is_word_char(c: str) -> bool:
    """Mirror of craft_proof::words(): alphanumeric, combining mark, or ' ’ -."""
    if c in WORD_PUNCT:
        return True
    cat = unicodedata.category(c)
    return cat[0] in ("L", "N") or cat[0] == "M"


_TABLE: dict[int, str] | None = None


def _table() -> dict[int, str]:
    """Every codepoint that is not a word character, mapped to a space (for str.translate)."""
    global _TABLE
    if _TABLE is None:
        t: dict[int, str] = {}
        for cp in range(0x110000):
            if 0xD800 <= cp <= 0xDFFF:
                continue
            if not is_word_char(chr(cp)):
                t[cp] = " "
        _TABLE = t
    return _TABLE


def tokens(text: str) -> list[str]:
    """The tokens craft-proof would see, in order (same character classes, same trimming)."""
    # str.translate is C-speed: mapping every non-word character to a space then splitting
    # gives the same result as the character loop in craft_proof::words(), ~50x faster.
    out = []
    for t in text.translate(_table()).split():
        t = t.strip(TRIM)
        if t:
            out.append(t)
    return out


def normalize(w: str, keep_diacritics: bool) -> str:
    """NFC (craft-proof composes before lookup), tatweel removed, harakat optional."""
    w = unicodedata.normalize("NFC", w).replace(TATWEEL, "")
    if not keep_diacritics:
        w = "".join(c for c in w if c not in HARAKAT)
    return unicodedata.normalize("NFC", w)


ARABIC_SCRIPT = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
HEBREW_SCRIPT = ((0x0590, 0x05FF), (0xFB1D, 0xFB4F))
ARABIC_LANGS = ("ar", "ckb", "fa", "ur", "sdh", "ps", "ku")


def script_ok(w: str, lang: str) -> bool:
    """Drop tokens that aren't this language's script: Latin residue, digits-only, emoji, and
    a neighbour's script (a Sorani corpus carries Hebrew and Latin quotations)."""
    if not w[0].isalpha():
        # "10ی", "123", "3rd": a word starts with a letter.
        return False
    if not any(c.isalpha() for c in w):
        return False
    if sum(c.isdigit() for c in w) > len(w) // 2:
        return False
    ranges = HEBREW_SCRIPT if lang == "he" else ARABIC_SCRIPT if lang in ARABIC_LANGS else ()
    if not ranges:
        return True
    # Sorani never starts a word with a bare hamza (U+0621): it uses ئ (yeh with hamza) or ا.
    # Every such token in a Kurdish corpus is a Quranic or Arabic quotation fragment
    # (`ءابآءكم` "your fathers"), which a Kurdish dictionary should not accept.
    if lang == "ckb" and w[0] == "\u0621":
        return False
    for c in w:
        if c.isalpha() and not any(lo <= ord(c) <= hi for lo, hi in ranges):
            return False
    return True


def read_words(path: Path) -> list[str]:
    """A plain word list: one per line, `#` comments, blank lines ignored."""
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def fetch(lang: str, articles: int, out: Path, batch: int = 50) -> None:
    """Plain-text extracts from <lang>.wikipedia.org, `batch` articles per request."""
    out.mkdir(parents=True, exist_ok=True)
    api = f"https://{lang}.wikipedia.org/w/api.php"
    got, cont, n = 0, None, 0
    while got < articles:
        q = {
            "action": "query", "format": "json", "generator": "allpages",
            "gapnamespace": "0", "gaplimit": str(batch),
            "prop": "extracts", "explaintext": "1", "exlimit": str(batch),
        }
        if cont:
            q.update(cont)
        url = api + "?" + urllib.parse.urlencode(q)
        req = urllib.request.Request(url, headers={"User-Agent": "wordcraft-dic-builder/1.0 (dictionary build)"})
        data = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == 4:
                    raise
                wait = 5 * (attempt + 1)
                print(f"  429, waiting {wait}s", flush=True)
                time.sleep(wait)
        pages = data.get("query", {}).get("pages", {})
        if not pages:
            break
        texts = [p.get("extract", "") for p in pages.values() if p.get("extract")]
        n += 1
        (out / f"batch-{n:04d}.txt").write_text("\n\n".join(texts), encoding="utf-8")
        got += len(texts)
        print(f"  {got} articles", flush=True)
        cont = data.get("continue")
        if not cont:
            break
        time.sleep(2.0)
    print(f"corpus in {out}")


def build(lang: str, corpus: Path, out: Path, min_freq: int, holdout: float,
          keep_diacritics: bool, max_words: int,
          extra: list[Path] | None = None, drop: list[Path] | None = None) -> None:
    files = sorted(corpus.glob("*.txt"))
    if not files:
        sys.exit(f"no .txt in {corpus}")
    # Hold out whole files, so the coverage report measures unseen text, not memorized text.
    cut = int(len(files) * (1 - holdout)) or 1
    train, test = files[:cut], files[cut:] or files[-1:]

    counts: Counter[str] = Counter()
    for f in train:
        for t in tokens(f.read_text(encoding="utf-8", errors="replace")):
            w = normalize(t, keep_diacritics)
            if 2 <= len(w) <= 40 and script_ok(w, lang):
                counts[w] += 1

    kept = [(w, n) for w, n in counts.items() if n >= min_freq]
    kept.sort(key=lambda x: (-x[1], x[0]))
    kept = kept[:max_words]
    words = set(w for w, _ in kept)

    # Corrections that survive a rebuild. The .dic is generated, so a hand edit to it is lost;
    # these two lists are the only supported way to fix an entry.
    added: list[str] = []
    for path in extra or []:
        for w in read_words(path):
            w = normalize(w, keep_diacritics)
            # Curated words skip the script and frequency filters: someone decided they belong.
            if w and w not in words:
                words.add(w)
                added.append(w)
    removed: list[str] = []
    for path in drop or []:
        for w in read_words(path):
            w = normalize(w, keep_diacritics)
            if w in words:
                words.discard(w)
                removed.append(w)
    words_sorted = sorted(words)

    out.mkdir(parents=True, exist_ok=True)
    (out / "spelling.dic").write_text(
        f"{len(words_sorted)}\n" + "\n".join(words_sorted) + "\n", encoding="utf-8")
    # A bare .aff: UTF-8, no affix rules. Full-form lists need none (SCOWL ships this way).
    (out / "spelling.aff").write_text(
        "# Generated by build_dic.py: a full-form word list, no affix rules.\n"
        "SET UTF-8\n", encoding="utf-8")

    # Check words: the most frequent words must pass; a doubled letter must fail.
    correct = [w for w, _ in kept[:8]]
    incorrect = []
    for w, _ in kept[:8]:
        if len(w) >= 3:
            incorrect.append(w + w[-1] * 3)
        if len(incorrect) >= 4:
            break
    (out / "checks.toml").write_text(
        "# Words the pack must accept and reject (generated from the corpus).\n"
        f"correct = {json.dumps(correct, ensure_ascii=False)}\n"
        f"incorrect = {json.dumps(incorrect, ensure_ascii=False)}\n", encoding="utf-8")

    # Coverage: what share of held-out tokens the dictionary knows, and what it rejects.
    known = set(words_sorted)
    total = miss = 0
    rejects: Counter[str] = Counter()
    for f in test:
        for t in tokens(f.read_text(encoding="utf-8", errors="replace")):
            w = normalize(t, keep_diacritics)
            if not (2 <= len(w) <= 40 and script_ok(w, lang)):
                continue
            total += 1
            if w not in known:
                miss += 1
                rejects[w] += 1
    rate = (100.0 * miss / total) if total else 0.0

    # Corrections are only worth anything if they landed: check every one.
    bad = [w for w in added if w not in known] + [w for w in removed if w in known]
    lines = [
        f"language          {lang}",
        f"corpus files      {len(files)} ({len(train)} train, {len(test)} held out)",
        f"distinct tokens   {len(counts)}",
        f"kept (>= {min_freq})    {len(kept)}",
        f"added (--extra)   {len(added)}",
        f"dropped (--drop)  {len(removed)}",
        f"dictionary words  {len(words_sorted)}",
        f"dictionary size   {(out / 'spelling.dic').stat().st_size:,} bytes",
        f"held-out tokens   {total:,}",
        f"unknown           {miss:,} ({rate:.2f}%)",
    ]
    if added:
        lines.append(f"  added:   {' '.join(added[:12])}{' …' if len(added) > 12 else ''}")
    if removed:
        lines.append(f"  dropped: {' '.join(removed[:12])}{' …' if len(removed) > 12 else ''}")
    lines += [f"corrections       {'OK' if not bad else 'FAILED: ' + ' '.join(bad)}"]
    lines += ["", "most frequent unknown tokens (add words or lower --min-freq):"]
    lines += [f"  {w}  x{n}" for w, n in rejects.most_common(20)]
    (out / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def wiki_clean(text: str) -> str:
    """Strip enough wiki markup that it doesn't become dictionary words."""
    text = re.sub(r"<ref[^>]*/>", " ", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", " ", text, flags=re.S)
    text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    text = re.sub(r"\{\|.*?\|\}", " ", text, flags=re.S)
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[https?://[^\]]*\]", " ", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^[=*#:;].*$", " ", text, flags=re.M)
    return text


def dump(path: Path, out: Path, per_file: int = 200, max_mb: int = 400) -> None:
    """Read a Wikipedia `pages-articles.xml.bz2` dump into plain-text corpus files."""
    import bz2
    out.mkdir(parents=True, exist_ok=True)
    buf: list[str] = []
    n = files = chars = 0
    with bz2.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for m in re.finditer(r"<text[^>]*>(.*?)</text>", f.read(), flags=re.S):
            body = m.group(1)
            if body.lstrip().upper().startswith("#REDIRECT"):
                continue
            body = wiki_clean(body)
            if len(body) < 40:
                continue
            buf.append(body)
            chars += len(body)
            n += 1
            if len(buf) >= per_file:
                files += 1
                (out / f"dump-{files:04d}.txt").write_text("\n\n".join(buf), encoding="utf-8")
                buf = []
            if chars > max_mb << 20:
                break
    if buf:
        files += 1
        (out / f"dump-{files:04d}.txt").write_text("\n\n".join(buf), encoding="utf-8")
    print(f"{n} articles, {chars:,} characters, {files} files in {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="download a corpus")
    f.add_argument("--lang", required=True, help="Wikipedia language code, e.g. ckb")
    f.add_argument("--articles", type=int, default=1000)
    f.add_argument("--out", type=Path, required=True)

    d = sub.add_parser("dump", help="read a Wikipedia pages-articles .xml.bz2 into plain text")
    d.add_argument("--dump", type=Path, required=True)
    d.add_argument("--out", type=Path, required=True)
    d.add_argument("--max-mb", type=int, default=400)

    b = sub.add_parser("build", help="build the dictionary")
    b.add_argument("--lang", required=True)
    b.add_argument("--corpus", type=Path, required=True)
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--min-freq", type=int, default=3, help="drop tokens seen fewer times (noise)")
    b.add_argument("--holdout", type=float, default=0.1, help="share of files held out for the report")
    b.add_argument("--keep-diacritics", action="store_true", help="keep harakat (off: strip them)")
    b.add_argument("--max-words", type=int, default=200_000)
    b.add_argument("--extra", type=Path, action="append", default=[],
                   help="words to add, one per line (repeatable); survives every rebuild")
    b.add_argument("--drop", type=Path, action="append", default=[],
                   help="words to remove, one per line (repeatable); survives every rebuild")

    args = ap.parse_args()
    if args.cmd == "fetch":
        fetch(args.lang, args.articles, args.out)
    elif args.cmd == "dump":
        dump(args.dump, args.out, max_mb=args.max_mb)
    else:
        build(args.lang, args.corpus, args.out, args.min_freq, args.holdout,
              args.keep_diacritics, args.max_words, args.extra, args.drop)


if __name__ == "__main__":
    main()
