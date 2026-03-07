#!/usr/bin/env python3
"""Fetch Trello cards from TiMilha boards and generate tarefas.html."""

import json
import os
import urllib.request
from datetime import datetime, timezone

API_KEY = os.environ["TRELLO_API_KEY"]
TOKEN = os.environ["TRELLO_TOKEN"]

BOARDS = {
    "social-media": {"id": "6994f474690cab72a6c4ebc2", "name": "Social Media &amp; Content"},
    "design-redes": {"id": "6994f4c181e83d2f04d70f09", "name": "Design Redes"},
    "design-fisico": {"id": "699a44e43cfd38ea363e4a29", "name": "Design Físico"},
}

LIST_ORDER = {
    "social-media": [
        ("6994f4789675a26dc800b96e", "To Do", "badge-todo"),
        ("6994f479093f02529cfebd63", "Doing", "badge-doing"),
        ("6994f47a46e8cd84d6f29421", "Done", "badge-done"),
        ("6994f47ba1999608d5cc1726", "Post Plan", "badge-plan"),
        ("699a47513cd2b66e6d524514", "Info &amp; Docs", "badge-info"),
        ("69a0bb9c2faf6c17a3cb5040", "Ideias", "badge-ideias"),
    ],
    "design-redes": [
        ("699a40104dffd182204a0dbf", "Post Plan", "badge-plan"),
        ("6994f4c181e83d2f04d70f2f", "To Do", "badge-todo"),
        ("6994f4c181e83d2f04d70f30", "Doing", "badge-doing"),
        ("6994f4c181e83d2f04d70f31", "Done", "badge-done"),
    ],
    "design-fisico": [
        ("699a542fef83f46597899fc7", "To Do", "badge-todo"),
        ("699a5433e194c0074dbb2e7d", "Doing", "badge-doing"),
        ("699a5434febfcaf96594f105", "Done", "badge-done"),
    ],
}

MEMBERS = {
    "5bcb1855ca515d26deab9ac2": ("Inês Rechau", "IR"),
    "696e8b7c41f81c653bf60df7": ("Mariana Lopes Marques", "ML"),
    "52884db7c38e32d4090011c2": ("Wilson Capitão", "WC"),
    "5dd29ca0123a480a7a7cf0a1": ("mafaldamp200", "MM"),
}

LABEL_CLASSES = {
    "instagram stories": "label-stories",
    "instagram feed": "label-feed",
    "post feed": "label-feed",
    "post stories": "label-stories",
    "data tbc": "label-tbc",
}

MONTHS_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}


def api_get(path, params=None):
    base = "https://api.trello.com/1"
    url = f"{base}/{path}?key={API_KEY}&token={TOKEN}"
    if params:
        url += "&" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def format_date_pt(iso_str):
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return f"{dt.day:02d} {MONTHS_PT[dt.month]} {dt.year}"


def date_class(iso_str):
    if not iso_str:
        return ""
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    diff = (dt - now).days
    if diff < 0:
        return "overdue"
    if diff <= 14:
        return "upcoming"
    return ""


def progress_class(done, total):
    if total == 0:
        return "low"
    pct = done / total
    if pct >= 0.75:
        return "high"
    if pct >= 0.25:
        return "mid"
    return "low"


def fetch_board_data(board_key):
    board_id = BOARDS[board_key]["id"]
    cards = api_get(f"boards/{board_id}/cards", {
        "fields": "name,desc,idList,labels,due,dateLastActivity,idMembers",
        "checklists": "all",
    })
    return cards


def render_checklist_items(checklists):
    items = []
    for cl in checklists:
        for item in cl.get("checkItems", []):
            done = item.get("state") == "complete"
            items.append((item.get("name", ""), done))
    return items


def render_card(card):
    name = card.get("name", "")
    desc = card.get("desc", "").strip()
    due = card.get("due")
    last_activity = card.get("dateLastActivity")
    member_ids = card.get("idMembers", [])
    labels = card.get("labels", [])
    checklists = card.get("checklists", [])
    short_url = f"https://trello.com/c/{card.get('shortLink', card.get('id', ''))}"

    # Build checklist items
    cl_items = render_checklist_items(checklists)
    done_count = sum(1 for _, d in cl_items if d)
    total_count = len(cl_items)
    pct = int((done_count / total_count * 100)) if total_count > 0 else 0

    html = f'        <div class="task-card" onclick="toggleCard(this)">\n'
    html += f'          <div class="task-summary">\n'
    html += f'            <div class="task-top"><div class="task-name">{esc(name)}</div><div class="task-arrow">▼</div></div>\n'

    # Meta row
    html += '            <div class="task-meta">\n'
    if due:
        dc = date_class(due)
        cls = f' {dc}' if dc else ''
        html += f'              <span class="task-due{cls}">{format_date_pt(due)}</span>\n'

    for label in labels:
        ln = (label.get("name") or "").strip()
        if not ln:
            continue
        lc = LABEL_CLASSES.get(ln.lower(), "label-tbc")
        html += f'              <span class="task-label {lc}">{esc(ln)}</span>\n'

    for mid in member_ids:
        if mid in MEMBERS:
            full, initials = MEMBERS[mid]
            html += f'              <span class="task-member"><span class="member-avatar">{initials}</span><span class="member-name">{esc(full)}</span></span>\n'

    if not due and not labels:
        html += '              <span class="task-label label-tbc">Sem data</span>\n'

    html += '            </div>\n'

    # Progress bar
    if total_count > 0:
        pc = progress_class(done_count, total_count)
        html += f'            <div class="progress-wrap"><div class="progress-bar"><div class="progress-fill {pc}" style="width:{pct}%"></div></div><span class="progress-text">{done_count}/{total_count}</span></div>\n'

    html += '          </div>\n'

    # Details (expandable)
    html += '          <div class="task-details">\n'

    if desc:
        html += '            <div class="detail-section">\n'
        html += '              <div class="detail-label">Descrição</div>\n'
        html += f'              <div class="detail-desc">{esc(desc)}</div>\n'
        html += '            </div>\n'

    if cl_items:
        html += '            <div class="detail-section">\n'
        html += '              <div class="detail-label">Checklist</div>\n'
        for item_name, item_done in cl_items:
            if item_done:
                html += f'              <div class="checklist-item done"><span class="check-icon">✓</span>{esc(item_name)}</div>\n'
            else:
                html += f'              <div class="checklist-item"><span class="check-icon"></span>{esc(item_name)}</div>\n'
        html += '            </div>\n'

    html += '            <div class="detail-row">\n'
    if last_activity:
        html += f'              <div class="detail-info"><strong>Última atividade:</strong> {format_date_pt(last_activity)}</div>\n'
    html += f'              <a href="{short_url}" target="_blank" class="trello-link">Abrir no Trello →</a>\n'
    html += '            </div>\n'
    html += '          </div>\n'
    html += '        </div>\n'
    return html


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def get_nav_logo():
    """Read logo from reunioes.html."""
    try:
        with open("reunioes.html", "r") as f:
            content = f.read()
        start = content.find('class="logo">')
        if start == -1:
            return ""
        img_start = content.find('src="', start) + 5
        img_end = content.find('"', img_start)
        return content[img_start:img_end]
    except Exception:
        return ""


def generate_html():
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    # Fetch all boards
    board_cards = {}
    board_totals = {}
    for key in BOARDS:
        cards = fetch_board_data(key)
        board_cards[key] = cards
        board_totals[key] = len(cards)

    logo_src = get_nav_logo()

    # Start building HTML
    html = f"""<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow, noarchive, nosnippet">
<title>Ti Milha — Tarefas Trello</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@300;400;500;600;700;800;900&family=Barlow:ital,wght@0,300;0,400;0,500;0,600;1,300;1,400&family=Courier+Prime:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="css/styles.css">
<style>
.tarefas-wrap{{max-width:1200px;margin:0 auto;padding:100px 40px 60px}}
.board-tabs{{display:flex;gap:2px;margin-bottom:40px;flex-wrap:wrap}}
.board-tab{{background:var(--surface);border:1px solid var(--border);padding:14px 24px;font-family:'Barlow Condensed',sans-serif;font-size:18px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;cursor:pointer;transition:all .2s;flex:1;text-align:center;min-width:180px}}
.board-tab:hover{{color:var(--cream);border-color:var(--cream)}}
.board-tab.active{{color:var(--gold);border-color:var(--gold);background:var(--card)}}
.board-tab .tab-count{{display:block;font-family:'Courier Prime',monospace;font-size:11px;color:var(--muted);margin-top:4px;letter-spacing:.1em}}
.board-content{{display:none}}.board-content.active{{display:block}}
.board-stats{{display:flex;gap:2px;margin-bottom:40px}}
.board-stat{{flex:1;padding:20px 24px;background:var(--surface);border:1px solid var(--border);text-align:center}}
.board-stat .stat-val{{font-family:'Barlow Condensed',sans-serif;font-size:38px;font-weight:800;color:var(--cream);line-height:1}}
.board-stat .stat-lbl{{font-family:'Courier Prime',monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-top:6px}}
.list-section{{margin-bottom:48px}}
.list-header{{display:flex;align-items:center;gap:12px;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--border)}}
.list-name{{font-family:'Barlow Condensed',sans-serif;font-size:24px;font-weight:800;color:var(--cream);text-transform:uppercase;letter-spacing:.04em}}
.list-badge{{font-family:'Courier Prime',monospace;font-size:11px;padding:3px 10px;letter-spacing:.1em;text-transform:uppercase}}
.badge-todo{{background:var(--border);color:var(--cream-dim)}}
.badge-doing{{background:var(--gold);color:var(--bg)}}
.badge-done{{background:var(--green);color:#fff}}
.badge-plan{{background:rgba(200,169,106,.15);color:var(--gold);border:1px solid var(--gold)}}
.badge-info{{background:rgba(74,140,92,.15);color:var(--green);border:1px solid var(--green)}}
.badge-ideias{{background:rgba(196,55,58,.15);color:var(--red);border:1px solid var(--red)}}
.task-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:2px}}
.task-card{{background:var(--surface);border:1px solid var(--border);transition:border-color .2s,background .2s;position:relative;overflow:hidden;cursor:pointer}}
.task-card:hover{{border-color:var(--cream);background:var(--card)}}
.task-card.expanded{{border-color:var(--gold);background:var(--card);grid-column:1/-1}}
.task-summary{{padding:20px;display:flex;flex-direction:column;gap:10px}}
.task-top{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}}
.task-name{{font-family:'Barlow Condensed',sans-serif;font-size:16px;font-weight:600;color:var(--cream);line-height:1.3;flex:1}}
.task-arrow{{color:var(--muted);font-size:14px;transition:transform .2s;flex-shrink:0;margin-top:2px}}
.task-card.expanded .task-arrow{{transform:rotate(180deg);color:var(--gold)}}
.task-meta{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.task-due{{font-family:'Courier Prime',monospace;font-size:11px;letter-spacing:.08em;color:var(--muted);text-transform:uppercase}}
.task-due.overdue{{color:var(--red)}}
.task-due.upcoming{{color:var(--gold)}}
.task-label{{font-family:'Courier Prime',monospace;font-size:10px;padding:2px 8px;letter-spacing:.08em;text-transform:uppercase;border-radius:2px}}
.label-feed{{background:rgba(200,169,106,.2);color:var(--gold)}}
.label-stories{{background:rgba(74,140,92,.2);color:var(--green)}}
.label-tbc{{background:rgba(196,55,58,.2);color:var(--red)}}
.task-member{{display:inline-flex;align-items:center;gap:6px}}
.member-avatar{{width:22px;height:22px;border-radius:50%;background:var(--gold);display:flex;align-items:center;justify-content:center;font-family:'Barlow Condensed',sans-serif;font-size:10px;font-weight:700;color:var(--bg);flex-shrink:0}}
.member-name{{font-family:'Courier Prime',monospace;font-size:10px;color:var(--muted);letter-spacing:.06em}}
.progress-wrap{{display:flex;align-items:center;gap:8px;width:100%}}
.progress-bar{{flex:1;height:4px;background:var(--border);border-radius:2px;overflow:hidden}}
.progress-fill{{height:100%;border-radius:2px;transition:width .3s}}
.progress-fill.low{{background:var(--red)}}
.progress-fill.mid{{background:var(--gold)}}
.progress-fill.high{{background:var(--green)}}
.progress-text{{font-family:'Courier Prime',monospace;font-size:10px;color:var(--muted);letter-spacing:.06em;white-space:nowrap}}
.task-details{{display:none;border-top:1px solid var(--border);padding:20px;background:rgba(0,0,0,.15)}}
.task-card.expanded .task-details{{display:block}}
.detail-section{{margin-bottom:16px}}.detail-section:last-child{{margin-bottom:0}}
.detail-label{{font-family:'Courier Prime',monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}}
.detail-desc{{font-size:13px;color:var(--text);line-height:1.7;white-space:pre-wrap}}
.checklist-item{{display:flex;align-items:flex-start;gap:8px;padding:4px 0;font-size:13px;color:var(--text)}}
.checklist-item.done{{color:var(--muted);text-decoration:line-through}}
.check-icon{{width:16px;height:16px;border:1px solid var(--border);border-radius:3px;flex-shrink:0;display:flex;align-items:center;justify-content:center;margin-top:2px;font-size:10px}}
.checklist-item.done .check-icon{{background:var(--green);border-color:var(--green);color:#fff}}
.detail-row{{display:flex;gap:24px;flex-wrap:wrap}}
.detail-info{{font-family:'Courier Prime',monospace;font-size:11px;color:var(--muted);letter-spacing:.06em}}
.detail-info strong{{color:var(--cream-dim)}}
.trello-link{{font-family:'Courier Prime',monospace;font-size:10px;color:var(--gold);text-decoration:none;letter-spacing:.08em;text-transform:uppercase;border:1px solid var(--gold);padding:4px 10px;display:inline-block;transition:all .2s}}
.trello-link:hover{{background:var(--gold);color:var(--bg)}}
.empty-board{{text-align:center;padding:60px 20px;background:var(--surface);border:1px solid var(--border)}}
.empty-board p{{font-family:'Courier Prime',monospace;font-size:13px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase}}
.updated-info{{font-family:'Courier Prime',monospace;font-size:10px;color:var(--muted);letter-spacing:.1em;text-transform:uppercase;text-align:right;margin-bottom:24px}}
@media(max-width:768px){{.tarefas-wrap{{padding:80px 20px 40px}}.board-tabs{{flex-direction:column}}.board-stats{{flex-direction:column}}.task-grid{{grid-template-columns:1fr}}.detail-row{{flex-direction:column;gap:8px}}}}
</style>
</head>
<body>

<nav>
  <a href="index.html" class="logo">
    <img src="{logo_src}" alt="Ti Milha" />
  </a>
  <ul class="nav-links">
    <li><a href="reunioes.html">Reuniões</a></li>
    <li><a href="estrategia.html">Estratégia</a></li>
    <li><a href="cartaz.html">Cartaz</a></li>
    <li><a href="orcamento.html">Orçamento</a></li>
    <li><a href="merch.html">Merch</a></li>
    <li><a href="equipa.html">Equipa</a></li>
    <li><a href="calendario.html">Calendário</a></li>
    <li><a href="tarefas.html" class="active">Tarefas</a></li>
  </ul>
  <div class="badge">Internal — 2026</div>
</nav>

<div class="tarefas-wrap">
  <div class="section-header">
    <div>
      <div class="section-label">Trello Boards — TiMilha Workspace</div>
      <div class="section-title">Tarefas</div>
    </div>
  </div>

  <div class="updated-info">Atualizado: {now_str}</div>

  <div class="board-tabs">
"""
    # Board tabs
    first = True
    for key in ["social-media", "design-redes", "design-fisico"]:
        active = " active" if first else ""
        html += f'    <div class="board-tab{active}" onclick="showBoard(\'{key}\')">{BOARDS[key]["name"]}<span class="tab-count">{board_totals[key]} tarefas</span></div>\n'
        first = False

    html += "  </div>\n\n"

    # Render each board
    first = True
    for key in ["social-media", "design-redes", "design-fisico"]:
        active = " active" if first else ""
        cards = board_cards[key]
        first = False

        html += f'  <div id="{key}" class="board-content{active}">\n'

        if not cards:
            html += '    <div class="empty-board"><p>Este board ainda não tem tarefas</p></div>\n'
            html += "  </div>\n\n"
            continue

        # Group cards by list
        lists_config = LIST_ORDER.get(key, [])
        cards_by_list = {}
        for card in cards:
            lid = card.get("idList", "")
            cards_by_list.setdefault(lid, []).append(card)

        # Stats
        list_counts = {lid: len(cards_by_list.get(lid, [])) for lid, _, _ in lists_config}
        html += '    <div class="board-stats">\n'
        html += f'      <div class="board-stat"><div class="stat-val">{len(cards)}</div><div class="stat-lbl">Total Tarefas</div></div>\n'
        for lid, lname, _ in lists_config:
            count = list_counts.get(lid, 0)
            if count > 0:
                html += f'      <div class="board-stat"><div class="stat-val">{count}</div><div class="stat-lbl">{lname}</div></div>\n'
        html += '    </div>\n\n'

        # Each list
        for lid, lname, badge_cls in lists_config:
            list_cards = cards_by_list.get(lid, [])
            if not list_cards:
                continue

            # Sort: cards with due dates first (by date), then no-date cards
            def sort_key(c):
                d = c.get("due")
                if d:
                    return (0, d)
                return (1, "")
            list_cards.sort(key=sort_key)

            count_label = f"{len(list_cards)} tarefa{'s' if len(list_cards) != 1 else ''}"

            html += '    <div class="list-section">\n'
            html += f'      <div class="list-header"><div class="list-name">{lname}</div><span class="list-badge {badge_cls}">{count_label}</span></div>\n'
            html += '      <div class="task-grid">\n'

            for card in list_cards:
                html += render_card(card)

            html += '      </div>\n'
            html += '    </div>\n\n'

        html += "  </div>\n\n"

    html += """</div>

<footer>
  <p>Ti Milha 2026 — Uso Interno Exclusivo &nbsp;·&nbsp; Equipa de Marketing</p>
  <p>-</p>
</footer>

<script>
function showBoard(id) {
  document.querySelectorAll('.board-content').forEach(function(b){b.classList.remove('active')});
  document.querySelectorAll('.board-tab').forEach(function(t){t.classList.remove('active')});
  document.getElementById(id).classList.add('active');
  event.currentTarget.classList.add('active');
}
function toggleCard(el) {
  el.classList.toggle('expanded');
}
</script>
</body>
</html>"""

    return html


if __name__ == "__main__":
    html = generate_html()
    with open("tarefas.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("tarefas.html generated successfully")
