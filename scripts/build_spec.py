#!/usr/bin/env python3
"""Build a montage spec from sections: [(hook_text, [(src, start, dur[, opts]), ...]), ...]."""
import json

SRC = {"P": "sources/PC Trailer.mp4", "D": "sources/DMZ WORLDBUILDER.mp4",
       "C": "sources/Campaign Trailer.mp4"}


def build(path, title, sections, cta, sub=("شغّل الصوت", 0)):
    shots, texts, t, spans = [], [], 0.0, []
    for hook, items in sections:
        st = t
        for it in items:
            d = {"src": SRC[it[0]], "start": float(it[1]), "dur": it[2]}
            if len(it) > 3:
                d.update(it[3])
            shots.append(d)
            t = round(t + it[2], 2)
        spans.append((st, t))
        if hook:
            texts.append({"from": st, "to": t, "style": "Hook", "text": hook})
    T = t
    texts = [{"from": 0, "to": T, "style": "Top", "text": title},
             {"from": 0.3, "to": spans[sub[1]][1], "style": "Sub", "text": sub[0]},
             {"from": T - 6, "to": T, "style": "CTA", "text": cta}] + texts
    json.dump({"font": "fonts/Cairo-Black.ttf", "shots": shots, "texts": texts},
              open(path, "w"), ensure_ascii=False, indent=2)
    return T
