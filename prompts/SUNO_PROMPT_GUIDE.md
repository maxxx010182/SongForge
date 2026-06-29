# SUNO_PROMPT_GUIDE.md

# SongForge Prompt Engineering Guide

## Цель

Данный документ содержит правила построения профессиональных промптов для Suno V5.5.

Он используется AI Prompt Builder.

Пользователь может вообще не знать, как работает Suno.

SongForge самостоятельно строит максимально качественный запрос.

---

# Главный принцип

Не использовать короткие промпты.

Плохой пример:

```
Epic music
```

Хороший пример:

```
Epic cinematic trailer, hybrid orchestra, emotional female vocal, huge choir, modern Hollywood production, powerful percussion, wide stereo image, dramatic build-up, emotional climax, crystal clear mix, immersive atmosphere.
```

---

# Структура профессионального Prompt

Всегда придерживаться порядка.

1.

Genre

↓

2.

Subgenre

↓

3.

Mood

↓

4.

Tempo

↓

5.

Energy

↓

6.

Instrumentation

↓

7.

Vocal

↓

8.

Production Style

↓

9.

Atmosphere

↓

10.

Mixing Quality

---

# Рекомендуемая схема

Genre

↓

Mood

↓

Energy

↓

Instrumentation

↓

Vocals

↓

Production

↓

Atmosphere

↓

References

---

# Genre

Использовать только реальные музыкальные жанры.

Например

Pop

Rock

EDM

Synthwave

Lo-Fi

Jazz

House

Future Bass

Cinematic

Epic

Hip-Hop

Country

Metal

Orchestral

Ambient

Phonk

Drum & Bass

Trap

Indie

Alternative

Soul

Funk

Blues

Classical

---

# Mood

Happy

Hopeful

Dark

Aggressive

Romantic

Emotional

Dreamy

Powerful

Epic

Energetic

Sad

Calm

Inspirational

Melancholic

---

# Tempo

Slow

Medium

Fast

Upbeat

Driving

Explosive

---

# Energy

Low

Medium

High

Extreme

---

# Instrumentation

Acoustic Guitar

Electric Guitar

Piano

Strings

Cello

Violin

Choir

Synth

Bass

808

Orchestra

Brass

Percussion

Drums

Hybrid Orchestra

Cinematic FX

Pads

---

# Vocal

Female Vocal

Male Vocal

Deep Male Vocal

Soft Female Vocal

Powerful Female Vocal

Emotional Vocal

Whisper Vocal

Choir

Children Choir

Duet

---

# Production

Hollywood Production

Modern Radio Mix

Wide Stereo

Crystal Clear Mix

Studio Quality

Professional Mastering

Clean Mixing

High Fidelity

Dynamic Range

---

# Atmosphere

Huge

Emotional

Warm

Cold

Dark

Dreamlike

Mystical

Space

Massive

Intimate

Vintage

Retro

Cyberpunk

Futuristic

---

# References

Использовать только описание стиля.

Не использовать названия артистов.

Правильно:

```
Modern cinematic trailer

Hollywood soundtrack

Radio pop production

Japanese anime opening

AAA game soundtrack
```

Неправильно:

```
Hans Zimmer

Imagine Dragons

Linkin Park
```

---

# Negative Tags

Использовать всегда.

Базовый список

```
low quality

noise

distortion

bad mix

clipping

overcompressed

monotone

muddy sound

poor vocal

off key

weak drums
```

---

# Style Weight

По умолчанию

```
0.85
```

---

# Weirdness

По умолчанию

```
0.20
```

Эксперимент

```
0.60
```

---

# Audio Weight

По умолчанию

```
0.70
```

---

# Prompt Quality Levels

## BASIC

Минимальный Prompt.

Использовать только при необходимости.

---

## GOOD

Использовать большинство параметров.

---

## PROFESSIONAL

Использовать всю структуру.

---

## CINEMATIC

Максимально насыщенный Prompt.

Использовать все доступные параметры.

---

# SongForge AI Builder

AI Builder автоматически:

✔ определяет жанр

✔ добавляет поджанр

✔ добавляет настроение

✔ определяет темп

✔ выбирает инструменты

✔ определяет голос

✔ строит профессиональный Style

✔ создаёт Negative Tags

✔ создаёт Title

✔ подбирает Style Weight

✔ подбирает Weirdness

✔ подбирает Audio Weight

---

# Главная цель

Каждый Prompt должен выглядеть так, как будто его написал профессиональный музыкальный продюсер, а не обычный пользователь.

SongForge никогда не отправляет в Suno "сырой" пользовательский запрос.

Любой пользовательский текст сначала проходит интеллектуальную обработку AI Prompt Builder, после чего превращается в максимально качественный профессиональный Prompt.
