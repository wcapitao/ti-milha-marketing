#!/usr/bin/env python3
"""Populate updates.html with weekly Ti Milha summaries from the knowledge base.

Deterministic data gathering (Python):
  - Collect WhatsApp messages from the 6 Ti Milha group folders (last 8 weeks).
  - Pull curated bullets from wiki/projects/ti-milha-marketing.md "Recent Updates".

LLM judgment (Claude Code CLI, print mode):
  - For each ISO week with activity, Claude returns a JSON summary with
    topics discussed, decisions taken, and action items — no quoted messages.

Summaries are cached in scripts/.updates-cache.json keyed by a SHA256 of the
week's raw inputs, so the generator only calls the LLM when content changes.

Splices HTML cards between the AUTO-UPDATES markers inside updates.html.
"""

import hashlib
import html
import json
import os
import pathlib
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
KB_ROOT = pathlib.Path(os.environ.get("KB_ROOT", "/home/athena/knowledge-base"))
WIKI_FILE = KB_ROOT / "wiki/projects/ti-milha-marketing.md"
WHATSAPP_ROOT = KB_ROOT / "raw/_whatsapp"
UPDATES_HTML = REPO_ROOT / "updates.html"
CACHE_FILE = REPO_ROOT / "scripts/.updates-cache.json"

MARKER_START = "<!-- AUTO-UPDATES-START -->"
MARKER_END = "<!-- AUTO-UPDATES-END -->"

# Group folder (WhatsApp JID prefix) → human-readable chat name.
CHAT_IDS = {
    "120363405671062742": "Nós os 4 do Marketing",
    "120363140430734236": "Marketing Ti Milha",
    "120363424004166391": "Design Ti Milha + Wilson",
    "351918478517-1573867322": "Chefes Ti Milha",
    "120363407202174310": "Influencers // Ti Milha",
    "120363425646419771": "Ti Milha Politburo",
}

WINDOW_WEEKS = 8
CLAUDE_MODEL = "claude-haiku-4-5"
CLAUDE_TIMEOUT_S = 120

WHATSAPP_MSG_RE = re.compile(r"\*\*\[(\d{2}:\d{2})\]\s+([^*]+?)\*\*:\s*(.+)")
FILENAME_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})")

MONTHS_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

SYSTEM_PROMPT = (
    "És um assistente de síntese para a equipa de marketing do Ti Milha "
    "(festival de música). Resumes conversas de WhatsApp em PORTUGUÊS "
    "EUROPEU (português de Portugal, PT-PT) — NUNCA em português do Brasil. "
    "Usa vocabulário e construções de Portugal: 'a equipa' (não 'o time'), "
    "'ecrã' (não 'tela'), 'autocarro' (não 'ônibus'), estás/estamos "
    "(não 'você está'), 'estás a fazer' (não 'está fazendo'), 'telemóvel' "
    "(não 'celular'), 'ficheiro' (não 'arquivo'). NUNCA cites mensagens "
    "diretamente. Respondes apenas com JSON válido — sem texto antes ou "
    "depois — no formato exato pedido."
)

USER_PROMPT_TEMPLATE = """Resume a atividade da equipa Ti Milha na semana de {start} a {end}.

INPUT (mensagens WhatsApp, um bloco por chat):
{messages}

{wiki_block}

INSTRUÇÕES:
- Escreve em PORTUGUÊS EUROPEU (PT-PT). NUNCA uses português do Brasil.
- Integra também as notas curadas da Knowledge Base no resumo (traduz para PT-PT se estiverem em inglês).
- NUNCA cites mensagens ou palavras diretas; parafraseia sempre.
- Não menciones nomes de pessoas individualmente — usa "a equipa", "os designers", "os chefes", etc.
- Agrupa em três categorias. Cada item tem 2 a 4 frases (aprox. 40–80 palavras) com DETALHE CONCRETO: o quê exatamente, o contexto/porquê, e qualquer especificidade relevante (cores propostas, nomes de materiais, bandas, datas, valores, plataformas). Evita generalidades vagas como "identidade visual" sem dizer o que está em causa — diz *qual* o problema, *qual* a alternativa discutida, *qual* a razão.
- Mantém cada item auto-contido (quem lê não tem outro contexto além do teu resumo).
- Agrupa itens relacionados num único item mais detalhado, em vez de vários itens curtos e repetitivos.
- Se uma categoria estiver vazia, devolve lista vazia.
- Devolve APENAS JSON válido com este schema exato:

{{
  "topicos": ["string", ...],
  "decisoes": ["string", ...],
  "acoes": ["string", ...]
}}"""

# ───────────────────────── Data gathering ─────────────────────────


def iso_week_key(d):
    """Return (ISO year, ISO week) tuple."""
    y, w, _ = d.isocalendar()
    return (y, w)


def week_bounds(year, week):
    """Monday–Sunday bounds of an ISO week as date objects."""
    monday = date.fromisocalendar(year, week, 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def collect_whatsapp_messages():
    """Yield dicts from the 6 Ti Milha chat folders within WINDOW_WEEKS."""
    if not WHATSAPP_ROOT.exists():
        return []
    cutoff = datetime.now() - timedelta(weeks=WINDOW_WEEKS)
    messages = []
    for chat_id, chat_name in CHAT_IDS.items():
        chat_dir = WHATSAPP_ROOT / chat_id
        if not chat_dir.exists():
            continue
        for md_file in chat_dir.glob("*.md"):
            if md_file.name == "_meta.md":
                continue
            fn_match = FILENAME_DATE_RE.search(md_file.name)
            if not fn_match:
                continue
            try:
                file_date = datetime(
                    int(fn_match.group(1)), int(fn_match.group(2)), int(fn_match.group(3)),
                    int(fn_match.group(4)), int(fn_match.group(5)),
                )
            except ValueError:
                continue
            if file_date < cutoff:
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for m in WHATSAPP_MSG_RE.finditer(text):
                time_str, sender, body = m.group(1), m.group(2).strip(), m.group(3).strip()
                try:
                    ts = file_date.replace(
                        hour=int(time_str[:2]), minute=int(time_str[3:]), second=0
                    )
                except ValueError:
                    ts = file_date
                messages.append({
                    "chat_name": chat_name,
                    "timestamp": ts,
                    "sender": sender,
                    "text": body,
                })
    return messages


def parse_wiki_recent_updates():
    """Return list of {date, text} from wiki 'Recent Updates' bullets."""
    if not WIKI_FILE.exists():
        return []
    content = WIKI_FILE.read_text(encoding="utf-8")
    m = re.search(r"### Recent Updates\s*\n(.+?)(?=\n###|\n## |\Z)", content, re.DOTALL)
    if not m:
        return []
    out = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        clean = re.sub(r"\s*\[Source:[^\]]+\]", "", line[2:]).strip()
        d, clean = _split_date_prefix(clean)
        if not d:
            continue
        out.append({"date": d, "text": clean})
    return out


def _split_date_prefix(text):
    m = re.match(
        r"\**(?:(\w+)\s+(\d{1,2}),\s+(\d{4})|(\w+)\s+(\d{4}))\**\s*[:\-–]\s*(.+)",
        text,
    )
    if not m:
        return None, text
    if m.group(1):
        month_name, day, year, rest = m.group(1), int(m.group(2)), int(m.group(3)), m.group(6)
    else:
        month_name, day, year, rest = m.group(4), 1, int(m.group(5)), m.group(6)
    month = _month_from_name(month_name)
    if not month:
        return None, text
    try:
        return date(year, month, day), rest.strip()
    except ValueError:
        return None, text


def _month_from_name(name):
    mapping = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
        "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    }
    return mapping.get(name.strip().lower())


# ───────────────────────── LLM summarisation ─────────────────────────


def cache_load():
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def cache_save(cache):
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def render_messages_block(messages):
    """Format messages deterministically as the LLM input. Grouped by chat."""
    by_chat = defaultdict(list)
    for msg in messages:
        by_chat[msg["chat_name"]].append(msg)
    lines = []
    for chat_name in sorted(by_chat.keys()):
        lines.append(f"=== {chat_name} ===")
        for msg in sorted(by_chat[chat_name], key=lambda x: x["timestamp"]):
            ts = msg["timestamp"].strftime("%Y-%m-%d %H:%M")
            lines.append(f"[{ts}] {msg['sender']}: {msg['text']}")
        lines.append("")
    return "\n".join(lines).strip()


def hash_inputs(messages, wiki_bullets):
    payload = {
        "messages": [
            (m["chat_name"], m["timestamp"].isoformat(), m["sender"], m["text"])
            for m in sorted(messages, key=lambda x: (x["timestamp"], x["sender"]))
        ],
        "wiki": sorted((w["date"].isoformat(), w["text"]) for w in wiki_bullets),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def summarise_week(year, week, messages, wiki_bullets):
    """Call Claude Code to summarise one week. Returns dict or None on failure."""
    start, end = week_bounds(year, week)
    messages_block = render_messages_block(messages) or "(sem mensagens WhatsApp esta semana)"
    wiki_block = ""
    if wiki_bullets:
        lines = ["CONTEXTO ADICIONAL (notas curadas da Knowledge Base):"]
        for w in sorted(wiki_bullets, key=lambda x: x["date"]):
            lines.append(f"- {w['date'].isoformat()}: {w['text']}")
        wiki_block = "\n".join(lines) + "\n"

    prompt = USER_PROMPT_TEMPLATE.format(
        start=start.isoformat(),
        end=end.isoformat(),
        messages=messages_block,
        wiki_block=wiki_block,
    )

    try:
        proc = subprocess.run(
            [
                "claude", "-p",
                "--model", CLAUDE_MODEL,
                "--output-format", "json",
                "--system-prompt", SYSTEM_PROMPT,
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT_S,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"  claude CLI failed for {year}-W{week:02d}: {e}", file=sys.stderr)
        return None

    if proc.returncode != 0:
        print(f"  claude exit {proc.returncode} for {year}-W{week:02d}: {proc.stderr[:300]}", file=sys.stderr)
        return None

    try:
        events = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        print(f"  claude stdout not JSON for {year}-W{week:02d}: {e}", file=sys.stderr)
        return None

    result_event = next((x for x in events if isinstance(x, dict) and x.get("type") == "result"), None)
    if not result_event or result_event.get("is_error"):
        print(f"  no result event for {year}-W{week:02d}", file=sys.stderr)
        return None

    text = result_event.get("result", "").strip()
    # Strip markdown code fences if Claude added them despite instructions.
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()
    try:
        summary = json.loads(text)
    except json.JSONDecodeError:
        print(f"  summary payload not JSON for {year}-W{week:02d}", file=sys.stderr)
        return None

    normalised = {
        "topicos": list(summary.get("topicos") or []),
        "decisoes": list(summary.get("decisoes") or []),
        "acoes": list(summary.get("acoes") or []),
    }
    return normalised


# ───────────────────────── Rendering ─────────────────────────


def render_cards(weekly_summaries):
    """Build the HTML block placed between the AUTO-UPDATES markers.

    weekly_summaries: list of dicts sorted newest-first with keys
      year, week, start, end, summary, msg_count, chat_names.
    """
    if not weekly_summaries:
        generated = datetime.now().strftime("%Y-%m-%d %H:%M")
        return (
            f'    <div style="padding:40px;text-align:center;color:var(--muted);">'
            f"Sem novidades recentes. (Gerado automaticamente em {generated})"
            f"</div>\n"
        )

    parts = []
    for i, wk in enumerate(weekly_summaries):
        parts.append(_render_week_card(wk, is_open=(i == 0)))
    return "\n".join(parts) + "\n"


def _fmt_day(d):
    return f"{d.day:02d} {MONTHS_PT[d.month]}"


def _render_week_card(wk, is_open):
    start, end = wk["start"], wk["end"]
    badge_day = f"W{wk['week']:02d}"
    badge_month = f"{end.year}"
    range_str = f"{_fmt_day(start)} – {_fmt_day(end)}"
    chats_str = ", ".join(wk["chat_names"]) if wk["chat_names"] else "sem chats com atividade"
    subtitle = f"{range_str} · {wk['msg_count']} mensagens · {chats_str}"

    open_cls = " open" if is_open else ""
    parts = [
        f'    <div class="meeting-card{open_cls}">',
        '      <div class="meeting-header" onclick="this.parentElement.classList.toggle(\'open\')">',
        '        <div class="meeting-header-left">',
        '          <div class="meeting-date-badge">',
        f'            <div class="mdb-day">{badge_day}</div>',
        f'            <div class="mdb-month">{html.escape(badge_month)}</div>',
        '          </div>',
        '          <div>',
        '            <div class="meeting-title">Resumo da Semana</div>',
        f'            <div class="meeting-subtitle">{html.escape(subtitle)}</div>',
        '          </div>',
        '        </div>',
        '        <div class="meeting-toggle">+</div>',
        '      </div>',
        '      <div class="meeting-body">',
        '        <div class="meeting-body-inner">',
    ]

    summary = wk["summary"]
    sections = [
        ("topicos", "Tópicos em Discussão", "&#128172;", "info", "tag-info"),
        ("decisoes", "Decisões", "&#9989;", "critical", "tag-decision"),
        ("acoes", "Ações em Curso", "&#128205;", "action", "tag-action"),
    ]

    empty = True
    for key, label, icon, point_cls, tag_cls in sections:
        items = summary.get(key, []) if summary else []
        if not items:
            continue
        empty = False
        parts.append('          <div class="meeting-category">')
        parts.append('            <div class="meeting-cat-title">')
        parts.append(f'              <div class="meeting-cat-icon">{icon}</div>')
        parts.append(f'              <div class="meeting-cat-label">{label}</div>')
        parts.append('            </div>')
        parts.append('            <ul class="meeting-points">')
        for item in items:
            parts.append(
                f'              <li class="meeting-point {point_cls}">{html.escape(str(item))}</li>'
            )
        parts.append('            </ul>')
        parts.append('          </div>')

    if empty:
        parts.append(
            '          <div style="padding:16px;color:var(--muted);font-size:13px;">'
            "Sem resumo disponível para esta semana."
            "</div>"
        )

    parts.append('        </div>')
    parts.append('      </div>')
    parts.append('    </div>')
    return "\n".join(parts)


# ───────────────────────── Splice ─────────────────────────


def splice(html_text, new_block):
    if MARKER_START not in html_text or MARKER_END not in html_text:
        raise SystemExit(
            f"Markers {MARKER_START} / {MARKER_END} not found in {UPDATES_HTML}"
        )
    pattern = re.compile(
        re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
        re.DOTALL,
    )
    replacement = f"{MARKER_START}\n{new_block}    {MARKER_END}"
    return pattern.sub(replacement, html_text, count=1)


# ───────────────────────── Main ─────────────────────────


def main():
    messages = collect_whatsapp_messages()
    wiki_bullets = parse_wiki_recent_updates()

    cache = cache_load()
    cache_dirty = False

    msgs_by_week = defaultdict(list)
    for msg in messages:
        msgs_by_week[iso_week_key(msg["timestamp"].date())].append(msg)

    wiki_by_week = defaultdict(list)
    for w in wiki_bullets:
        wiki_by_week[iso_week_key(w["date"])].append(w)

    active_weeks = set(msgs_by_week) | set(wiki_by_week)
    weekly_summaries = []

    for (year, week) in sorted(active_weeks, reverse=True):
        wk_msgs = msgs_by_week.get((year, week), [])
        wk_wiki = wiki_by_week.get((year, week), [])
        input_hash = hash_inputs(wk_msgs, wk_wiki)
        cache_key = f"{year}-W{week:02d}"

        cached = cache.get(cache_key)
        if cached and cached.get("input_hash") == input_hash:
            summary = cached.get("summary")
        elif wk_msgs or wk_wiki:
            print(f"Summarising {cache_key} ({len(wk_msgs)} msgs, {len(wk_wiki)} KB notes)...")
            summary = summarise_week(year, week, wk_msgs, wk_wiki)
            if summary is not None:
                cache[cache_key] = {"input_hash": input_hash, "summary": summary}
                cache_dirty = True
            elif cached:
                summary = cached.get("summary")  # fall back to stale
        else:
            summary = {"topicos": [], "decisoes": [], "acoes": []}

        start, end = week_bounds(year, week)
        chat_names = sorted({m["chat_name"] for m in wk_msgs})
        weekly_summaries.append({
            "year": year,
            "week": week,
            "start": start,
            "end": end,
            "summary": summary,
            "msg_count": len(wk_msgs),
            "chat_names": chat_names,
            "wiki_bullets": wk_wiki,
        })

    if cache_dirty:
        cache_save(cache)

    block = render_cards(weekly_summaries)
    current = UPDATES_HTML.read_text(encoding="utf-8")
    updated = splice(current, block)

    if updated != current:
        UPDATES_HTML.write_text(updated, encoding="utf-8")
        print(f"updates.html refreshed: {len(weekly_summaries)} week(s).")
    else:
        print("updates.html unchanged.")


if __name__ == "__main__":
    main()
