# Getting ckb into craft-i18n — the short version

Six steps. Steps 1–3 are yours, step 4 is the ask, steps 5–6 are theirs.

## 1. Put this folder on GitHub

Create an **empty public repo** named `craft-ckb-data`, then from this folder:

```sh
git init
git add .
git commit -m "Sorani (ckb) spelling word list from the 2026-11-01 ckbwiki dump"
git branch -M main
git remote add origin https://github.com/<you>/craft-ckb-data.git
git push -u origin main
```

Do not use the GitHub web "upload files" button for `ckb.dic` if it complains about size — 2.6 MB
is fine either way, but a normal `git push` is simpler.

## 2. Get the commit hash

```sh
git rev-parse HEAD
```

That prints 40 characters. That is the `<SHA>` in `manifest-snippet.toml`. A branch name would
*look* like it works, but it moves; the hash is what makes the pin permanent.

## 3. Check the URL opens

Paste this in a browser, with your values:

```
https://raw.githubusercontent.com/<you>/craft-ckb-data/<SHA>/ckb.dic
```

You must see the word list, not a 404. If it 404s, the repo is private or the SHA is wrong.

## 4. Open the issue

Use `ISSUE.md` in this folder. Add one line near the top:

> The files are pinned and ready at `https://raw.githubusercontent.com/<you>/craft-ckb-data/<SHA>/`.

The question you are asking them is not "please host my data" — it is "is a *generated* list
acceptable as a Download-only pack, pinned from a third-party repo?" That is a policy call only
they can make.

## 5. If they say yes: the pull request

Three files change in craft-i18n:

| File | What to add |
|---|---|
| `language-data/manifest.toml` | the three entries from `manifest-snippet.toml` |
| `language-data/checks/ckb.toml` | copy `checks/ckb.toml` from this folder (8 correct, 4 incorrect words) |
| `ATTRIBUTION.md` | one row per file: Wikipedia contributors, the dump URL, the sha256, `CC-BY-SA-4.0`, `Download-only` |

Run `cargo test --workspace` — it must pass offline (no network). Then the CI workflow
`language-packs.yml` verifies the sha256s on its weekly run.

## 6. What happens after they merge

Their release workflow builds `ckb.tar.zst` from your pinned files, and it ships in the next
`language-packs-<n>`. From then on a user needs no folder copying: **File › Options › Language ›
Add a language…** → type *kurdish* → **Install**.

## If they say no

Nothing is wasted. Publish your own release with `ckb.tar.zst` + `index.json` (see the `GUIDE.md`
in the WordCraft workspace, section 5), and users install it by pointing `CRAFT_LANGUAGE_PACK_INDEX` at
your index, or by copying the folder — which already works today.
