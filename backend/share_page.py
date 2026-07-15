"""Публичная страница трека /t/{id} — шаринг как YouTube/Instagram.

Слушать + обложка + плеер. Без скачивания. CTA на платформу.
OG-мета — превью в Telegram / WhatsApp.
"""

from __future__ import annotations

import html
import json
from typing import Any


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _abs_url(site_url: str, path_or_url: str) -> str:
    raw = (path_or_url or "").strip()
    base = (site_url or "").rstrip("/")
    if not raw:
        return f"{base}/assets/apple-touch-icon.png"
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.startswith("//"):
        return "https:" + raw
    return f"{base}/{raw.lstrip('/')}"


def render_share_track_page(
    *,
    site_url: str,
    library_id: str,
    title: str,
    author_name: str,
    image_url: str,
    likes: int = 0,
) -> str:
    site = (site_url or "").rstrip("/")
    tid = (library_id or "").strip()
    title_s = (title or "").strip() or "Без названия"
    author_s = (author_name or "").strip() or "Аноним"
    img = _abs_url(site, image_url)
    listen = f"/api/explore/{tid}/listen"
    share = f"{site}/t/{tid}"
    create_url = f"{site}/?from=share"
    explore_url = f"{site}/?track={tid}"

    desc = f"«{title_s}» — {author_s} · слушай на СоздайСвоюПесню"

    payload = {
        "id": tid,
        "title": title_s,
        "author": author_s,
        "image": img,
        "listen": listen,
        "share": share,
    }
    payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>{_esc(title_s)} — {_esc(author_s)} | СоздайСвоюПесню</title>
<meta name="description" content="{_esc(desc)}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{_esc(share)}">
<meta property="og:type" content="music.song">
<meta property="og:site_name" content="СоздайСвоюПесню">
<meta property="og:title" content="{_esc(title_s)}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{_esc(share)}">
<meta property="og:image" content="{_esc(img)}">
<meta property="og:image:alt" content="{_esc(title_s)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{_esc(title_s)}">
<meta name="twitter:description" content="{_esc(desc)}">
<meta name="twitter:image" content="{_esc(img)}">
<link rel="icon" href="/assets/favicon-32.png" type="image/png" sizes="32x32">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png" sizes="180x180">
<meta name="theme-color" content="#09090b">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{
  font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
  min-height:100vh;color:#f4f4f5;
  background:#09090b;
  background-image:radial-gradient(ellipse 80% 50% at 50% 0%,rgba(234,179,8,.12),transparent 60%);
}}
a{{color:#eab308;text-decoration:none}}
a:hover{{text-decoration:underline}}
.wrap{{max-width:420px;margin:0 auto;padding:24px 16px 48px}}
.brand{{display:flex;align-items:center;gap:10px;margin-bottom:28px}}
.brand-mark{{
  width:36px;height:36px;flex-shrink:0;background:#eab308;
  -webkit-mask:url(/assets/logo_new.png) center/contain no-repeat;
  mask:url(/assets/logo_new.png) center/contain no-repeat;
}}
.brand-text{{font-weight:700;font-size:1.05rem;letter-spacing:-.03em;color:#eab308}}
.card{{
  background:rgba(24,24,27,.85);border:1px solid rgba(255,255,255,.08);
  border-radius:24px;overflow:hidden;
  box-shadow:0 24px 64px rgba(0,0,0,.45);
}}
.cover-wrap{{position:relative;aspect-ratio:1;background:#18181b}}
.cover-wrap img{{width:100%;height:100%;object-fit:cover;display:block}}
.eq{{
  position:absolute;left:0;right:0;bottom:0;height:38%;
  display:flex;align-items:flex-end;justify-content:center;gap:3px;
  padding:0 18% 14px;
  background:linear-gradient(to top,rgba(0,0,0,.7),transparent);
  opacity:0;transition:opacity .25s;pointer-events:none;
}}
.eq.on{{opacity:1}}
.eq span{{
  flex:1;max-width:7px;height:22%;min-height:8px;border-radius:2px;
  background:linear-gradient(to top,#ca8a04,#eab308,#fef08a);
}}
.eq.on span{{animation:eq .9s ease-in-out infinite}}
.eq span:nth-child(2){{animation-delay:.08s}}.eq span:nth-child(3){{animation-delay:.16s}}
.eq span:nth-child(4){{animation-delay:.04s}}.eq span:nth-child(5){{animation-delay:.2s}}
.eq span:nth-child(6){{animation-delay:.12s}}.eq span:nth-child(7){{animation-delay:.18s}}
.eq span:nth-child(8){{animation-delay:.1s}}
@keyframes eq{{0%,100%{{height:18%}}25%{{height:55%}}50%{{height:100%}}75%{{height:40%}}}}
.meta{{padding:20px 20px 8px}}
.title{{font-size:1.35rem;font-weight:700;line-height:1.25;margin-bottom:6px;word-break:break-word}}
.author{{font-size:.9rem;color:#a1a1aa;margin-bottom:8px}}
.likes{{font-size:.75rem;color:#71717a}}
.player{{padding:12px 20px 20px}}
.controls{{display:flex;align-items:center;gap:12px;margin-bottom:12px}}
.btn-play{{
  width:56px;height:56px;border-radius:18px;border:none;cursor:pointer;
  background:#eab308;color:#09090b;font-size:1.25rem;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
  box-shadow:0 8px 24px rgba(234,179,8,.35);
}}
.btn-play:hover{{filter:brightness(1.08)}}
.btn-play:disabled{{opacity:.5;cursor:wait}}
.times{{flex:1;min-width:0}}
.seek{{width:100%;height:6px;accent-color:#eab308;cursor:pointer}}
.time-row{{display:flex;justify-content:space-between;font-size:.7rem;color:#71717a;margin-top:6px}}
.hint{{font-size:.72rem;color:#52525b;text-align:center;margin-top:10px;line-height:1.4}}
.actions{{padding:0 20px 22px;display:flex;flex-direction:column;gap:10px}}
.btn{{
  display:block;text-align:center;padding:14px 16px;border-radius:14px;
  font-size:.9rem;font-weight:600;border:none;cursor:pointer;text-decoration:none;
}}
.btn-primary{{background:#eab308;color:#09090b}}
.btn-primary:hover{{filter:brightness(1.06);text-decoration:none}}
.btn-ghost{{background:rgba(255,255,255,.06);color:#e4e4e7;border:1px solid rgba(255,255,255,.1)}}
.btn-ghost:hover{{background:rgba(255,255,255,.1);text-decoration:none}}
.toast{{
  position:fixed;left:50%;bottom:24px;transform:translateX(-50%) translateY(80px);
  background:#27272a;color:#fafafa;padding:10px 16px;border-radius:12px;
  font-size:.85rem;opacity:0;transition:.25s;z-index:20;pointer-events:none;
  border:1px solid rgba(255,255,255,.1);
}}
.toast.show{{opacity:1;transform:translateX(-50%) translateY(0)}}
.foot{{margin-top:28px;text-align:center;font-size:.75rem;color:#52525b;line-height:1.5}}
</style>
</head>
<body>
<div class="wrap">
  <a class="brand" href="{_esc(site)}/">
    <span class="brand-mark" aria-hidden="true"></span>
    <span class="brand-text">СоздайСвоюПесню</span>
  </a>

  <div class="card">
    <div class="cover-wrap">
      <img id="cover" src="{_esc(img)}" alt="{_esc(title_s)}"
           onerror="this.onerror=null;this.src='/assets/apple-touch-icon.png'">
      <div class="eq" id="eq" aria-hidden="true">
        <span></span><span></span><span></span><span></span>
        <span></span><span></span><span></span><span></span>
      </div>
    </div>
    <div class="meta">
      <h1 class="title" id="title">{_esc(title_s)}</h1>
      <div class="author" id="author">{_esc(author_s)}</div>
      <div class="likes">{int(likes or 0)} ❤ на МузПлощадке</div>
    </div>
    <div class="player">
      <div class="controls">
        <button type="button" class="btn-play" id="playBtn" aria-label="Слушать">▶</button>
        <div class="times">
          <input type="range" class="seek" id="seek" min="0" max="100" value="0" step="1" aria-label="Позиция">
          <div class="time-row"><span id="tCur">0:00</span><span id="tTot">0:00</span></div>
        </div>
      </div>
      <p class="hint">Можно слушать и смотреть обложку.<br>Скачивание — только у автора в фонотеке.</p>
    </div>
    <div class="actions">
      <a class="btn btn-primary" href="{_esc(create_url)}">Создать свою песню</a>
      <button type="button" class="btn btn-ghost" id="copyBtn">Скопировать ссылку</button>
      <a class="btn btn-ghost" href="{_esc(explore_url)}">Открыть на платформе</a>
    </div>
  </div>

  <p class="foot">AI-студия: идея → текст → трек · sozdaipesnu.ru</p>
</div>
<div class="toast" id="toast"></div>
<audio id="audio" preload="metadata" playsinline controlsList="nodownload noplaybackrate"></audio>
<script>
(function(){{
  var T = {payload_json};
  var audio = document.getElementById('audio');
  var playBtn = document.getElementById('playBtn');
  var seek = document.getElementById('seek');
  var tCur = document.getElementById('tCur');
  var tTot = document.getElementById('tTot');
  var eq = document.getElementById('eq');
  var toast = document.getElementById('toast');
  var seeking = false;

  audio.src = T.listen;
  // не отдаём прямую «скачать как файл» через UI
  audio.setAttribute('controlsList', 'nodownload noplaybackrate');

  function fmt(s){{
    s = Math.max(0, Math.floor(s || 0));
    var m = Math.floor(s / 60), r = s % 60;
    return m + ':' + (r < 10 ? '0' : '') + r;
  }}
  function setEq(on){{ eq.classList.toggle('on', !!on); }}
  function showToast(msg){{
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(function(){{ toast.classList.remove('show'); }}, 2200);
  }}

  playBtn.addEventListener('click', function(){{
    if (audio.paused) {{
      audio.play().then(function(){{
        playBtn.textContent = '❚❚';
        setEq(true);
      }}).catch(function(){{
        showToast('Нажмите play ещё раз');
      }});
    }} else {{
      audio.pause();
      playBtn.textContent = '▶';
      setEq(false);
    }}
  }});

  audio.addEventListener('play', function(){{ playBtn.textContent = '❚❚'; setEq(true); }});
  audio.addEventListener('pause', function(){{ playBtn.textContent = '▶'; setEq(false); }});
  audio.addEventListener('ended', function(){{
    playBtn.textContent = '▶';
    setEq(false);
    seek.value = 0;
    tCur.textContent = '0:00';
  }});
  audio.addEventListener('loadedmetadata', function(){{
    var d = audio.duration;
    if (isFinite(d) && d > 0) {{
      seek.max = Math.floor(d);
      tTot.textContent = fmt(d);
    }}
  }});
  audio.addEventListener('timeupdate', function(){{
    if (seeking) return;
    var d = audio.duration, c = audio.currentTime;
    if (isFinite(d) && d > 0) {{
      seek.max = Math.floor(d);
      seek.value = Math.floor(c);
      tTot.textContent = fmt(d);
    }}
    tCur.textContent = fmt(c);
  }});
  audio.addEventListener('error', function(){{
    showToast('Не удалось загрузить аудио');
    playBtn.disabled = false;
  }});

  seek.addEventListener('input', function(){{
    seeking = true;
    tCur.textContent = fmt(parseInt(seek.value, 10) || 0);
  }});
  seek.addEventListener('change', function(){{
    try {{ audio.currentTime = parseInt(seek.value, 10) || 0; }} catch (e) {{}}
    seeking = false;
  }});

  document.getElementById('copyBtn').addEventListener('click', function(){{
    var url = T.share;
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(url).then(function(){{
        showToast('Ссылка скопирована');
      }}).catch(function(){{ prompt('Скопируйте ссылку:', url); }});
    }} else {{
      prompt('Скопируйте ссылку:', url);
    }}
  }});

  // Блок «сохранить аудио» через контекстное меню — полностью не убрать,
  // но прямого download в UI нет.
}})();
</script>
</body>
</html>
"""
