Language data: how should a **generated** dictionary be pinned? (Sorani, `ckb`)

---

I have a working Sorani (Central Kurdish) spelling dictionary for WordCraft, built as a
`Download-only` Language pack, and I'd like to know whether it can come into this repository and
in what shape. It does not fit the current manifest, and I think the reason is worth a decision
rather than a workaround.

## What it is

| | |
|---|---|
| Locale | `ckb` (کوردی) |
| Words | 160,349 |
| `spelling.dic` | 2.72 MB, sha256 `b1249f1d5133283b3527213afe00261ca02f74d515cc279e4d5337c49c087bef` |
| Pack | 447,055 bytes, sha256 `1b85fcdaf55d08eda1564afb90ecfdbde934b35fabde2a83a28121c168b554ad` |
| Licence | `CC-BY-SA-4.0`, class `Download-only` |
| Built from | `ckbwiki` dump of 2026-11-01 (121,884 articles, 178 M characters) |
| Quality | 5.11 % of held-out tokens unknown, 3.39 % measured through `craft-proof` |

It loads and proof-checks in WordCraft today (a real pack in the font store, marks and
suggestions working), and the `.aff` is just `SET UTF-8` — a full-form list, the way SCOWL ships.

## Why it doesn't fit

Three things, and the first is the blocker:

**1. `check_pinned_url` requires a raw GitHub file.**
`crates/craft-i18n-tests/src/packs.rs:18` fixes the host:

```rust
const HOST: &str = "https://raw.githubusercontent.com/";
```

The corpus is a Wikimedia dump (`https://dumps.wikimedia.org/ckbwiki/20261101/…`), which cannot
be written as `<owner>/<repo>/<commit>/<path>`. The generated `.dic` is not an upstream file at
all — there is nothing to pin.

**2. The data cannot be committed.** `language-data/README.md`: *"Nothing in a pack is committed; a
release workflow downloads, checks and publishes them."* So the file has no home in the tree.

**3. ADR 0004 has no category for it.** The rule is *"Files are never modified"* / unmodified
upstream files; a corpus-derived word list is neither upstream nor unmodified.

## Options I can see

**A. Pin a generated file from a data repository (works with the checker as written).**
I publish `<owner>/craft-ckb-data` holding the generated `.aff`/`.dic` plus a README with the
build command and corpus provenance, and the manifest pins
`https://raw.githubusercontent.com/<owner>/craft-ckb-data/<commit>/ckb.dic`. No format change; the
data lives outside this repo, which arguably honours the "nothing in a pack is committed" rule.
The weakness is that the pin attests to my repository, not to the corpus.

**B. A `generated` provenance kind.** A manifest entry that names the corpus and the tool instead
of an upstream file — e.g. `kind = "spelling-dic"`, `generated = true`, with `corpus-url`,
`corpus-date`, `tool` (name + commit) and the `sha256` of the output. The checker would accept a
non-GitHub URL only for such entries, and `sha256` + `size` would stay mandatory. This is honest
about what the file is and keeps the audit trail, but it is an ADR 0004/0005 change and a checker
change.

**C. Keep it self-hosted.** I publish my own release and `index.json`; users install it with
`CRAFT_LANGUAGE_PACK_INDEX` or by dropping the folder in. No changes here, but the pack is then
unpinned, unverified by your CI, and invisible to `language-packs-<n>`.

I would prefer **B**, then **A**. **C** is what I have now.

## What I'd contribute, if wanted

- the `[[file]]` entries in `language-data/manifest.toml` (or whatever B settles on),
- `language-data/checks/ckb.toml` — already written, 8 correct / 4 incorrect words,
- the `ATTRIBUTION.md` row (author: Wikipedia contributors; source; sha256; `CC-BY-SA-4.0`;
  `Download-only`),
- the generator, so the list is reproducible rather than a binary artefact
  (`build_dic.py`: dump → tokens → frequency → `.dic`, ~250 lines, with the corrections file
  that carries hand-reviewed additions and removals).

## Questions

1. Is a generated dictionary acceptable here at all, or is this repository deliberately limited to
   unmodified upstream files?
2. If acceptable: A or B — or something else you'd rather see?
3. Is `CC-BY-SA-4.0` / `Download-only` the class you want for a Wikipedia-derived list, or would
   you rather it stay out of the release entirely?

Not part of this issue, but found while building it: `accepted_by_options`
(`craft-libs`, `crates/proof/src/lib.rs:692`) tests `c.is_ascii_digit()`, so Arabic-Indic digits
(`٢٣ی`, "the 23rd") are flagged even with *Ignore words that contain numbers* on — relevant to
`ar`, `fa`, `ckb` and `ur` alike. I can file that separately against `craft-libs` if useful.
