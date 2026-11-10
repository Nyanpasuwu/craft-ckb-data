Sorani Kurdish (ckb) spelling word list for WordCraft
=====================================================

Source
------
Derived from the Sorani Wikipedia dump of 2026-11-01:
  https://dumps.wikimedia.org/ckbwiki/20261101/ckbwiki-20261101-pages-articles.xml.bz2
  (121,884 articles, 177,944,920 characters)

The dump's text was processed into a word list: tokenised, NFC-normalised, tatweel and harakat
removed, filtered to Arabic-script tokens, counted, and cut at a minimum frequency of 3. No article
text is included; the output is a list of distinct word forms only.

Changes from the source, as CC BY-SA 4.0 requires stating: the text was reduced to word forms and
filtered; a small number of words were added and removed by hand (see ckb-extra.txt and
ckb-drop.txt). Nothing was copied verbatim beyond individual words.

Contents
--------
  ckb.dic          160,349 words, UTF-8, one per line; first line is the count (Hunspell format)
  ckb.aff          "SET UTF-8" and nothing else: a full-form list, so no affix rules are needed
  build_dic.py     the generator, so this list can be reproduced or audited
  ckb-extra.txt    words added by hand (modern loanwords the corpus lacks)
  ckb-drop.txt     words removed by hand (junk that survived the frequency filter)

Rebuild
-------
  curl -O https://dumps.wikimedia.org/ckbwiki/20261101/ckbwiki-20261101-pages-articles.xml.bz2
  python build_dic.py dump  --dump ckbwiki-20261101-pages-articles.xml.bz2 --out corpus/ckb
  python build_dic.py build --lang ckb --corpus corpus/ckb --out ckb --min-freq 3 \
      --extra ckb-extra.txt --drop ckb-drop.txt
  # ckb/spelling.dic must hash to b1249f1d5133283b3527213afe00261ca02f74d515cc279e4d5337c49c087bef

Quality
-------
5.11 % of held-out tokens (10 % of the corpus files, never used for counting) are unknown, and
3.39 % measured through craft-proof on a 2.5 MB sample. Almost all of the remainder are proper
nouns the corpus never saw.

Licence
-------
CC BY-SA 4.0. See LICENCE.txt. Attribution: Wikipedia contributors, Sorani Wikipedia.
