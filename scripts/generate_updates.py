#!/usr/bin/env python3
"""Populate updates.html with the latest Ti Milha activity from the knowledge base.

Sources (all deterministic — no LLM):
  1. wiki/projects/ti-milha-marketing.md  → curated "Recent Updates" entries
  2. raw/_whatsapp/**/*.md                → recent messages mentioning Ti Milha

The script rewrites only the region bounded by
    <!-- AUTO-UPDATES-START -->  ...  <!-- AUTO-UPDATES-END -->
inside updates.html, preserving nav/footer and any archived meeting cards below.
"""

import html
import os
import pathlib
import re
from collections import defaultdict
from datetime import datetime, timedelta

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
KB_ROOT = pathlib.Path(os.environ.get("KB_ROOT", "/home/athena/knowledge-base"))
WIKI_FILE = KB_ROOT / "wiki/projects/ti-milha-marketing.md"
WHATSAPP_ROOT = KB_ROOT / "raw/_whatsapp"
UPDATES_HTML = REPO_ROOT / "updates.html"

MARKER_START = "<!-- AUTO-UPDATES-START -->"
MARKER_END = "<!-- AUTO-UPDATES-END -->"

WHATSAPP_WINDOW_DAYS = 30
WHATSAPP_PATTERN = re.compile(r"\bti[\s\.]?milha\b|\btimilha\b", re.IGNORECASE)
WHATSAPP_MSG_RE = re.compile(r"\*\*\[(\d{2}:\d{2})\]\s+([^*]+?)\*\*:\s*(.+)")
FILENAME_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})")

MONTHS_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

# ──────────────────────────── Source parsers ────────────────────────────


def parse_wiki_recent_updates():
    """Return list of (date, text, source_path) from the 'Recent Updates' list."""
    if not WIKI_FILE.exists():
        return []
    content = WIKI_FILE.read_text(encoding="utf-8")
    # Grab the "### Recent Updates" section
    m = re.search(r"### Recent Updates\s*\n(.+?)(?=\n###|\n## |\Z)", content, re.DOTALL)
    if not m:
        return []
    block = m.group(1)

    out = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        # Extract: date prefix + text + optional [Source: ...]
        # Pattern examples:
        #   - **April 13, 2026**: Save the date post published ... [Source: raw/_whatsapp/...]
        #   - April 2026: "Calendário Post Plan" tab added ... [Source: ...]
        sources = re.findall(r"\[Source:\s*([^\]]+)\]", line)
        clean = re.sub(r"\s*\[Source:[^\]]+\]", "", line[2:]).strip()
        date_obj, clean = _split_date_prefix(clean)
        if not date_obj:
            continue
        out.append({
            "date": date_obj,
            "text": clean,
            "sources": sources,
            "origin": "wiki",
        })
    return out


def _split_date_prefix(text):
    """Pull a leading date like '**April 13, 2026**: foo' or 'March 2026: foo'."""
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
        return datetime(year, month, day), rest.strip()
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


def parse_whatsapp_mentions():
    """Return list of entries from WhatsApp raw files mentioning Ti Milha."""
    if not WHATSAPP_ROOT.exists():
        return []
    cutoff = datetime.now() - timedelta(days=WHATSAPP_WINDOW_DAYS)
    entries = []
    for md_file in WHATSAPP_ROOT.rglob("*.md"):
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
        if not WHATSAPP_PATTERN.search(text):
            continue

        chat_name = _extract_chat_name(text) or md_file.parent.name
        for m in WHATSAPP_MSG_RE.finditer(text):
            time_str, sender, message = m.group(1), m.group(2).strip(), m.group(3).strip()
            if not WHATSAPP_PATTERN.search(message):
                continue
            entries.append({
                "date": file_date.replace(hour=int(time_str[:2]), minute=int(time_str[3:])),
                "text": message,
                "sender": sender,
                "chat": chat_name,
                "sources": [str(md_file.relative_to(KB_ROOT))],
                "origin": "whatsapp",
            })
    return entries


def _extract_chat_name(text):
    m = re.search(r"^#\s*WhatsApp:\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else None


# ──────────────────────────── Rendering ────────────────────────────


def render_cards(wiki_entries, wa_entries):
    """Return the inner HTML that goes between the AUTO-UPDATES sentinels."""
    # Group entries by date (day granularity), keep both sources separated per day.
    by_day = defaultdict(lambda: {"wiki": [], "whatsapp": []})
    for e in wiki_entries:
        by_day[e["date"].date()]["wiki"].append(e)
    for e in wa_entries:
        by_day[e["date"].date()]["whatsapp"].append(e)

    if not by_day:
        generated = datetime.now().strftime("%Y-%m-%d %H:%M")
        return (
            f'    <div style="padding:40px;text-align:center;color:var(--muted);">'
            f"Sem novidades recentes. (Gerado automaticamente em {generated})"
            f"</div>\n"
        )

    lines = []
    for i, day in enumerate(sorted(by_day.keys(), reverse=True)):
        bucket = by_day[day]
        lines.append(_render_card(day, bucket, is_open=(i == 0)))
    return "\n".join(lines) + "\n"


def _render_card(day, bucket, is_open):
    day_str = f"{day.day:02d}"
    mon_str = f"{MONTHS_PT[day.month]} {day.year}"
    wa_count = len(bucket["whatsapp"])
    wiki_count = len(bucket["wiki"])
    subtitle_parts = []
    if wiki_count:
        subtitle_parts.append(f"{wiki_count} nota(s) da KB")
    if wa_count:
        subtitle_parts.append(f"{wa_count} mensagem(ns) WhatsApp")
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else "Sem atividade"

    open_cls = " open" if is_open else ""
    parts = [
        f'    <div class="meeting-card{open_cls}">',
        '      <div class="meeting-header" onclick="this.parentElement.classList.toggle(\'open\')">',
        '        <div class="meeting-header-left">',
        '          <div class="meeting-date-badge">',
        f'            <div class="mdb-day">{day_str}</div>',
        f'            <div class="mdb-month">{html.escape(mon_str)}</div>',
        '          </div>',
        '          <div>',
        '            <div class="meeting-title">Updates do dia</div>',
        f'            <div class="meeting-subtitle">{html.escape(subtitle)}</div>',
        '          </div>',
        '        </div>',
        '        <div class="meeting-toggle">+</div>',
        '      </div>',
        '      <div class="meeting-body">',
        '        <div class="meeting-body-inner">',
    ]

    if bucket["wiki"]:
        parts.append('          <div class="meeting-category">')
        parts.append('            <div class="meeting-cat-title">')
        parts.append('              <div class="meeting-cat-icon">&#128221;</div>')
        parts.append('              <div class="meeting-cat-label">Knowledge Base</div>')
        parts.append('            </div>')
        parts.append('            <ul class="meeting-points">')
        for e in bucket["wiki"]:
            parts.append(
                f'              <li class="meeting-point info">{html.escape(e["text"])} '
                f'<span class="point-tag tag-info">KB</span></li>'
            )
        parts.append('            </ul>')
        parts.append('          </div>')

    if bucket["whatsapp"]:
        parts.append('          <div class="meeting-category">')
        parts.append('            <div class="meeting-cat-title">')
        parts.append('              <div class="meeting-cat-icon">&#128172;</div>')
        parts.append('              <div class="meeting-cat-label">WhatsApp</div>')
        parts.append('            </div>')
        parts.append('            <ul class="meeting-points">')
        for e in sorted(bucket["whatsapp"], key=lambda x: x["date"]):
            sender = html.escape(e["sender"])
            chat = html.escape(e["chat"])
            msg = html.escape(e["text"])
            time_str = e["date"].strftime("%H:%M")
            parts.append(
                f'              <li class="meeting-point action">'
                f'<strong>{sender}</strong> <em style="color:var(--muted);font-style:normal;">'
                f'({chat}, {time_str})</em>: {msg}</li>'
            )
        parts.append('            </ul>')
        parts.append('          </div>')

    parts.append('        </div>')
    parts.append('      </div>')
    parts.append('    </div>')
    return "\n".join(parts)


# ──────────────────────────── Splice into HTML ────────────────────────────


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


def main():
    wiki_entries = parse_wiki_recent_updates()
    wa_entries = parse_whatsapp_mentions()
    block = render_cards(wiki_entries, wa_entries)

    current = UPDATES_HTML.read_text(encoding="utf-8")
    updated = splice(current, block)

    if updated != current:
        UPDATES_HTML.write_text(updated, encoding="utf-8")
        print(
            f"updates.html refreshed: {len(wiki_entries)} KB note(s), "
            f"{len(wa_entries)} WhatsApp mention(s)."
        )
    else:
        print("updates.html unchanged.")


if __name__ == "__main__":
    main()
