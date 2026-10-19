"""Публичная страница подарка /g/{id} — открытка, не витрина."""

from __future__ import annotations

import json

from backend.share_page import _abs_url, _esc


THEMES = {
    "family": {
        "bg": "#120e0a",
        "accent": "#e8b86d",
        "accent2": "#f3d19a",
        "glow": "rgba(232,184,109,.28)",
        "photo": "/assets/gift/family.jpg",
        "photo_wide": "/assets/gift/family-wide.jpg",
    },
    "love": {
        "bg": "#14080a",
        "accent": "#e0707e",
        "accent2": "#f0a0a8",
        "glow": "rgba(201,75,92,.32)",
        "photo": "/assets/gift/love.jpg",
        "photo_wide": "/assets/gift/love-wide.jpg",
    },
    "birthday": {
        "bg": "#14110a",
        "accent": "#f5c542",
        "accent2": "#ffe08a",
        "glow": "rgba(245,197,66,.3)",
        "photo": "/assets/gift/birthday.jpg",
        "photo_wide": "/assets/gift/birthday-wide.jpg",
    },
    "simple": {
        "bg": "#09090b",
        "accent": "#eab308",
        "accent2": "#facc15",
        "glow": "rgba(234,179,8,.22)",
        "photo": "/assets/gift/simple.jpg",
        "photo_wide": "/assets/gift/simple-wide.jpg",
    },
}

_CSS = """
:root{--bg:@@BG@@;--accent:@@ACCENT@@;--accent2:@@ACCENT2@@;--glow:@@GLOW@@;--photo:url('@@PHOTO@@');--photo-wide:url('@@PHOTO_WIDE@@');}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:var(--bg);color:#f7f1ea;font-family:Inter,system-ui,sans-serif}
.scene{
  min-height:100dvh;
  display:flex;flex-direction:column;
  padding:max(18px,env(safe-area-inset-top)) 20px max(22px,env(safe-area-inset-bottom));
  background-color:var(--bg);
  background-image:linear-gradient(180deg,rgba(0,0,0,.38),rgba(0,0,0,.58)),var(--photo);
  background-size:cover;
  background-position:center;
  position:relative;
  overflow:hidden;
}
.fxlayer{position:fixed;inset:0;pointer-events:none;overflow:hidden;z-index:1}
.fx{position:absolute;bottom:-12%;color:var(--accent2);opacity:0;animation-name:drift;animation-timing-function:linear;animation-iteration-count:infinite;font-style:normal;line-height:1}
.fx.c{width:var(--s);height:calc(var(--s)*0.6);background:var(--accent);border-radius:2px;color:transparent}
.fx.d{width:var(--s);height:var(--s);border-radius:50%;background:var(--accent2)}
.fx.h{font-size:var(--s);text-shadow:0 0 12px var(--glow)}
@keyframes drift{
  from{transform:translate3d(0,0,0) rotate(0deg);opacity:0}
  12%{opacity:.55}
  to{transform:translate3d(28px,-115vh,0) rotate(160deg);opacity:0}
}
.brand{position:relative;z-index:2;display:flex;align-items:center;justify-content:center;gap:8px;color:rgba(255,255,255,.62);font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;margin-bottom:18px}
.brand span{width:7px;height:7px;border-radius:50%;background:var(--accent);display:inline-block}
.stage{position:relative;z-index:2;flex:1;width:min(100%,420px);max-width:100%;margin:0 auto;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:22px;text-align:center}
.copy{width:100%;min-width:0;max-width:100%}
.to{font-family:Unbounded,Inter,sans-serif;font-size:1.45rem;font-weight:600;color:#fff;letter-spacing:-.02em;line-height:1.25;margin:0;width:100%;padding:0 4px;overflow-wrap:break-word;text-shadow:0 8px 28px rgba(0,0,0,.55)}
.player{width:100%;min-width:0;max-width:100%;display:flex;flex-direction:column;align-items:center}
.cover{width:min(100%,280px);aspect-ratio:1;margin:0 auto 16px;border-radius:24px;overflow:hidden;border:1px solid rgba(255,255,255,.16);box-shadow:0 22px 48px rgba(0,0,0,.45),0 0 0 8px rgba(255,255,255,.06)}
.cover img{width:100%;height:100%;object-fit:cover;display:block}
.title{font-family:Unbounded,Inter,sans-serif;font-size:1.15rem;font-weight:500;margin:0 0 10px;line-height:1.3}
.play{width:78px;height:78px;border:0;border-radius:50%;background:var(--accent);color:#1c140c;font-size:1.45rem;cursor:pointer;box-shadow:0 12px 32px var(--glow)}
.play:hover{filter:brightness(1.06)}
.seek{width:100%;max-width:280px;accent-color:var(--accent);margin-top:16px;height:4px}
.times{display:flex;justify-content:space-between;font-size:.7rem;color:rgba(255,255,255,.55);margin-top:10px;width:100%;max-width:280px}
.sign{font-family:Caveat,cursive;font-size:1.65rem;color:var(--accent2);margin:18px 0 0;min-height:1.2em}
.sign.is-empty{display:none}
.foot{position:relative;z-index:2;margin-top:22px;text-align:center;font-size:.7rem;color:rgba(255,255,255,.42);line-height:1.5}
.foot a{color:rgba(255,255,255,.62);text-decoration:none}
@media (min-width:768px) and (max-width:859px){
  .scene{padding:max(28px,env(safe-area-inset-top)) 36px 36px}
  .stage{width:min(100%,540px);gap:28px}
  .to{font-size:2.15rem}
  .cover{width:min(100%,340px)}
  .seek,.times{max-width:340px}
}
@media (min-width:860px){
  .scene{
    padding:40px 56px 36px;
    background-image:linear-gradient(90deg,rgba(0,0,0,.5) 0%,rgba(0,0,0,.28) 46%,rgba(0,0,0,.4) 100%),var(--photo-wide);
  }
  .stage{width:min(1120px,100%);flex-direction:row;align-items:center;justify-content:space-between;gap:72px;text-align:left}
  .copy{flex:1}
  .to{font-size:clamp(2.2rem,4vw,3.3rem)}
  .player{flex:0 0 min(360px,38vw)}
  .cover{width:100%;max-width:340px}
  .title{font-size:1.35rem}
  .seek,.times{max-width:100%}
  .sign{font-size:2rem}
}
@media (prefers-reduced-motion:reduce){
  .fx{display:none}
}
"""

_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>@@HEADING@@ | @@TITLE@@</title>
<meta name="description" content="@@DESC@@">
<meta name="robots" content="noindex,follow">
<link rel="canonical" href="@@SHARE@@">
<meta property="og:type" content="website">
<meta property="og:site_name" content="СоздайСвоюПесню">
<meta property="og:title" content="@@HEADING@@">
<meta property="og:description" content="@@DESC@@">
<meta property="og:url" content="@@SHARE@@">
<meta property="og:image" content="@@OG@@">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:type" content="image/jpeg">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="@@HEADING@@">
<meta name="twitter:description" content="@@DESC@@">
<meta name="twitter:image" content="@@OG@@">
<link rel="image_src" href="@@OG@@">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Caveat:wght@500;600&family=Inter:wght@400;500&family=Unbounded:wght@500;600&display=swap">
<style>@@CSS@@</style>
</head>
<body>
<div class="scene">
  <div class="fxlayer" aria-hidden="true">@@FX@@</div>
  <a class="brand" href="@@SITE@@/"><span></span>СоздайСвоюПесню</a>
  <div class="stage">
    <div class="copy">
      <h1 class="to">@@HEADING@@</h1>
    </div>
    <div class="player">
      <div class="cover"><img src="@@IMG@@" alt="@@TITLE@@"></div>
      <h2 class="title">@@TITLE@@</h2>
      <button type="button" class="play" id="play" aria-label="Слушать">▶</button>
      <input type="range" class="seek" id="seek" min="0" max="100" value="0">
      <div class="times"><span id="tCur">0:00</span><span id="tTot">0:00</span></div>
      <p class="sign @@SIGN_HIDDEN@@">@@SIGN@@</p>
    </div>
  </div>
  <p class="foot"><a href="@@SITE@@/">СоздайСвоюПесню</a></p>
</div>
<audio id="audio" preload="metadata" playsinline></audio>
<script>
(function(){
  var T = @@PAYLOAD@@;
  var audio = document.getElementById('audio');
  var play = document.getElementById('play');
  var seek = document.getElementById('seek');
  var tCur = document.getElementById('tCur');
  var tTot = document.getElementById('tTot');
  audio.src = T.listen;
  function fmt(s){s=Math.max(0,s||0); var m=Math.floor(s/60); var sec=Math.floor(s%60); return m+':'+(sec<10?'0':'')+sec;}
  function sync(){
    if (audio.duration) {
      tTot.textContent = fmt(audio.duration);
      seek.value = String((audio.currentTime / audio.duration) * 100);
    }
    tCur.textContent = fmt(audio.currentTime);
  }
  play.addEventListener('click', function(){
    if (audio.paused) { audio.play(); play.textContent = '❚❚'; }
    else { audio.pause(); play.textContent = '▶'; }
  });
  audio.addEventListener('timeupdate', sync);
  audio.addEventListener('loadedmetadata', sync);
  audio.addEventListener('ended', function(){ play.textContent = '▶'; });
  seek.addEventListener('input', function(){
    if (!audio.duration) return;
    audio.currentTime = (Number(seek.value) / 100) * audio.duration;
  });
})();
</script>
</body>
</html>
"""


def _theme(occasion: str) -> dict[str, str]:
    return THEMES.get(occasion) or THEMES["simple"]


def _fx_html(occasion: str) -> str:
    kind = {"birthday": "c", "love": "h", "family": "d", "simple": "d"}.get(
        occasion, "d"
    )
    bits: list[str] = []
    for i in range(16):
        left = (i * 37 + 9) % 100
        delay = (i * 0.41) % 7
        dur = 9 + (i % 5)
        size = 5 + (i % 7)
        inner = "♥" if kind == "h" else ""
        bits.append(
            f'<i class="fx {kind}" style="left:{left}%;animation-delay:{delay:.2f}s;'
            f'animation-duration:{dur}s;--s:{size}px">{inner}</i>'
        )
    return "".join(bits)


def _fill(template: str, mapping: dict[str, str]) -> str:
    out = template
    for key, value in mapping.items():
        out = out.replace(f"@@{key}@@", value)
    return out


def render_gift_bot_page(
    *,
    site_url: str,
    gift_id: str,
    title: str,
    to_line: str,
    dedication: str,
    image_url: str,
    og_image: str = "",
) -> str:
    site = (site_url or "").rstrip("/")
    title_s = (title or "").strip() or "Песня"
    heading = (to_line or "").strip() or "Тебе"
    desc = f"{heading}. {title_s}"
    if dedication:
        desc = f"{heading}. {dedication}. {title_s}"
    share = f"{site}/g/{gift_id}"
    og = og_image or f"{site}/g/{gift_id}/og.jpg"
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>{_esc(heading)} | {_esc(title_s)}</title>
<meta name="description" content="{_esc(desc)}">
<meta name="robots" content="noindex,follow">
<link rel="canonical" href="{_esc(share)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="СоздайСвоюПесню">
<meta property="og:title" content="{_esc(heading)}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{_esc(share)}">
<meta property="og:image" content="{_esc(og)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:type" content="image/jpeg">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{_esc(heading)}">
<meta name="twitter:description" content="{_esc(desc)}">
<meta name="twitter:image" content="{_esc(og)}">
<link rel="image_src" href="{_esc(og)}">
</head>
<body>
<h1>{_esc(heading)}</h1>
<p>{_esc(title_s)}</p>
<p>{_esc(dedication)}</p>
<p><a href="{_esc(share)}">Открыть подарок</a></p>
</body>
</html>
"""


def render_gift_page(
    *,
    site_url: str,
    gift_id: str,
    title: str,
    to_line: str,
    from_line: str,
    dedication: str,
    occasion: str,
    image_url: str,
    og_image: str = "",
) -> str:
    site = (site_url or "").rstrip("/")
    theme = _theme(occasion)
    title_s = (title or "").strip() or "Песня"
    heading = (to_line or "").strip() or "Тебе"
    sign = (from_line or "").strip() or (dedication or "").strip()
    img = _abs_url(site, image_url)
    share = f"{site}/g/{gift_id}"
    listen = f"/api/gift/{gift_id}/listen"
    og = og_image or f"{site}/g/{gift_id}/og.jpg"
    desc = f"{heading}. {title_s}"
    if sign:
        desc = f"{heading}. {sign}. {title_s}"
    payload = json.dumps({"listen": listen, "title": title_s}, ensure_ascii=False)
    css = _fill(
        _CSS,
        {
            "BG": theme["bg"],
            "ACCENT": theme["accent"],
            "ACCENT2": theme["accent2"],
            "GLOW": theme["glow"],
            "PHOTO": theme["photo"],
            "PHOTO_WIDE": theme["photo_wide"],
        },
    )
    return _fill(
        _PAGE,
        {
            "CSS": css,
            "HEADING": _esc(heading),
            "TITLE": _esc(title_s),
            "DESC": _esc(desc),
            "SHARE": _esc(share),
            "OG": _esc(og),
            "SITE": _esc(site),
            "IMG": _esc(img),
            "SIGN": _esc(sign),
            "SIGN_HIDDEN": "is-empty" if not sign else "",
            "FX": _fx_html(occasion),
            "PAYLOAD": payload,
        },
    )
