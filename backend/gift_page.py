"""Публичная страница подарка /g/{id} — письмо, не витрина."""

from __future__ import annotations

import json

from backend.share_page import _abs_url, _esc


THEMES = {
    "family": {
        "bg": "#120e0a",
        "accent": "#e8b86d",
        "accent2": "#f3d19a",
        "glow": "rgba(232,184,109,.22)",
    },
    "love": {
        "bg": "#14080a",
        "accent": "#e0707e",
        "accent2": "#f0a0a8",
        "glow": "rgba(201,75,92,.28)",
    },
    "birthday": {
        "bg": "#14110a",
        "accent": "#f5c542",
        "accent2": "#ffe08a",
        "glow": "rgba(245,197,66,.26)",
    },
    "simple": {
        "bg": "#09090b",
        "accent": "#eab308",
        "accent2": "#facc15",
        "glow": "rgba(234,179,8,.18)",
    },
}


def _theme(occasion: str) -> dict[str, str]:
    return THEMES.get(occasion) or THEMES["simple"]


def render_gift_bot_page(
    *,
    site_url: str,
    gift_id: str,
    title: str,
    to_line: str,
    dedication: str,
    image_url: str,
) -> str:
    site = (site_url or "").rstrip("/")
    title_s = (title or "").strip() or "Песня"
    heading = (to_line or "").strip() or "Тебе"
    desc = f"{heading}. {title_s}"
    if dedication:
        desc = f"{heading}. {dedication}. {title_s}"
    share = f"{site}/g/{gift_id}"
    og_image = f"{site}/g/{gift_id}/og.jpg"
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
<meta property="og:image" content="{_esc(og_image)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{_esc(heading)}">
<meta name="twitter:description" content="{_esc(desc)}">
<meta name="twitter:image" content="{_esc(og_image)}">
</head>
<body>
<h1>{_esc(heading)}</h1>
<p>{_esc(title_s)}</p>
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
) -> str:
    site = (site_url or "").rstrip("/")
    theme = _theme(occasion)
    title_s = (title or "").strip() or "Песня"
    heading = (to_line or "").strip() or "Тебе"
    dedication_s = (dedication or "").strip()
    img = _abs_url(site, image_url)
    share = f"{site}/g/{gift_id}"
    listen = f"/api/gift/{gift_id}/listen"
    og_image = f"{site}/g/{gift_id}/og.jpg"
    desc = f"{heading}. {title_s}"
    if dedication_s:
        desc = f"{heading}. {dedication_s}. {title_s}"
    payload = json.dumps(
        {"listen": listen, "title": title_s},
        ensure_ascii=False,
    )
    sparkle_css = ""
    if occasion == "birthday":
        sparkle_css = """.card::after{content:'';position:absolute;inset:0;pointer-events:none;background-image:radial-gradient(1px 1px at 18% 22%,rgba(255,255,255,.45),transparent),radial-gradient(1px 1px at 78% 18%,rgba(255,224,138,.5),transparent),radial-gradient(1px 1px at 64% 78%,rgba(255,255,255,.28),transparent);border-radius:28px}"""
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{_esc(heading)} | {_esc(title_s)}</title>
<meta name="description" content="{_esc(desc)}">
<meta name="robots" content="noindex,follow">
<link rel="canonical" href="{_esc(share)}">
<meta property="og:type" content="website">
<meta property="og:title" content="{_esc(heading)}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{_esc(share)}">
<meta property="og:image" content="{_esc(og_image)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=Space+Grotesk:wght@500;600&display=swap">
<style>
:root{{--bg:{theme['bg']};--accent:{theme['accent']};--accent2:{theme['accent2']};--glow:{theme['glow']};}}
*{{box-sizing:border-box}}
html,body{{margin:0;min-height:100%;background:var(--bg);color:#f4efe8;font-family:Inter,system-ui,sans-serif}}
body{{min-height:100dvh;padding:max(20px,env(safe-area-inset-top)) 20px max(24px,env(safe-area-inset-bottom));background-image:radial-gradient(ellipse 80% 50% at 50% 0%,var(--glow),transparent 62%),linear-gradient(180deg,var(--bg),#070707);}}
.wrap{{max-width:420px;margin:0 auto;}}
.brand{{display:flex;align-items:center;justify-content:center;gap:8px;color:#a8a29e;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;text-decoration:none;margin-bottom:28px}}
.brand span{{width:7px;height:7px;border-radius:50%;background:var(--accent);display:inline-block}}
.card{{border-radius:28px;padding:22px 20px 26px;background:rgba(18,16,14,.62);border:1px solid rgba(255,255,255,.08);backdrop-filter:blur(18px);box-shadow:0 24px 60px rgba(0,0,0,.35);text-align:center}}
.to{{font-family:'Space Grotesk',sans-serif;font-size:1.35rem;font-weight:600;color:var(--accent2);letter-spacing:-.02em;margin:0 0 16px;animation:rise .7s ease both}}
.cover{{width:min(100%,280px);aspect-ratio:1;margin:0 auto 18px;border-radius:22px;overflow:hidden;border:1px solid rgba(255,255,255,.12);box-shadow:0 18px 40px rgba(0,0,0,.4);animation:rise .8s .08s ease both}}
.cover img{{width:100%;height:100%;object-fit:cover;display:block}}
.title{{font-family:'Space Grotesk',sans-serif;font-size:1.45rem;margin:0 0 8px;line-height:1.25;animation:rise .8s .12s ease both}}
.ded{{color:#d6d3d1;font-size:.95rem;min-height:1.4em;margin:0 0 22px;animation:rise .8s .16s ease both}}
.play{{width:76px;height:76px;border:0;border-radius:50%;background:var(--accent);color:#1c140c;font-size:1.4rem;cursor:pointer;box-shadow:0 12px 32px var(--glow);animation:rise .8s .2s ease both}}
.play:hover{{filter:brightness(1.06)}}
.times{{display:flex;justify-content:space-between;font-size:.7rem;color:#78716c;margin-top:14px}}
.seek{{width:100%;accent-color:var(--accent);margin-top:16px;height:4px}}
.foot{{margin-top:28px;text-align:center;font-size:.72rem;color:#57534e;line-height:1.5}}
.foot a{{color:#a8a29e;text-decoration:none}}
{sparkle_css}
.card{{position:relative}}
@keyframes rise{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:none}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
@media (min-width:768px){{.wrap{{max-width:440px;padding-top:24px}}.to{{font-size:1.5rem}}}}
</style>
</head>
<body>
<div class="wrap">
  <a class="brand" href="{_esc(site)}/"><span></span>СоздайСвоюПесню</a>
  <div class="card">
    <h1 class="to">{_esc(heading)}</h1>
    <div class="cover"><img src="{_esc(img)}" alt="{_esc(title_s)}"></div>
    <h2 class="title">{_esc(title_s)}</h2>
    <p class="ded">{_esc(dedication_s)}</p>
    <button type="button" class="play" id="play" aria-label="Слушать">▶</button>
    <input type="range" class="seek" id="seek" min="0" max="100" value="0">
    <div class="times"><span id="tCur">0:00</span><span id="tTot">0:00</span></div>
  </div>
  <p class="foot">Песню собрали как подарок.<br><a href="{_esc(site)}/">СоздайСвоюПесню</a></p>
</div>
<audio id="audio" preload="metadata" playsinline></audio>
<script>
(function(){{
  var T = {payload};
  var audio = document.getElementById('audio');
  var play = document.getElementById('play');
  var seek = document.getElementById('seek');
  var tCur = document.getElementById('tCur');
  var tTot = document.getElementById('tTot');
  audio.src = T.listen;
  function fmt(s){{s=Math.max(0,s||0); var m=Math.floor(s/60); var sec=Math.floor(s%60); return m+':'+(sec<10?'0':'')+sec;}}
  function sync(){{
    if (audio.duration) {{
      tTot.textContent = fmt(audio.duration);
      seek.value = String((audio.currentTime / audio.duration) * 100);
    }}
    tCur.textContent = fmt(audio.currentTime);
  }}
  play.addEventListener('click', function(){{
    if (audio.paused) {{ audio.play(); play.textContent = '❚❚'; }}
    else {{ audio.pause(); play.textContent = '▶'; }}
  }});
  audio.addEventListener('timeupdate', sync);
  audio.addEventListener('loadedmetadata', sync);
  audio.addEventListener('ended', function(){{ play.textContent = '▶'; }});
  seek.addEventListener('input', function(){{
    if (!audio.duration) return;
    audio.currentTime = (Number(seek.value) / 100) * audio.duration;
  }});
}})();
</script>
</body>
</html>
"""
