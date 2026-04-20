#!/usr/bin/env python3
"""Fetch Trello cards from TiMilha boards and generate tarefas.html."""

import json
import os
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

LISBON = ZoneInfo("Europe/Lisbon")

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
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(LISBON)
    return f"{dt.day:02d} {MONTHS_PT[dt.month]} {dt.year}"


def date_class(iso_str):
    if not iso_str:
        return ""
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(LISBON)
    now = datetime.now(LISBON)
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


def build_calendar_data(board_cards):
    """Extract Post Plan cards from social-media board for the calendar."""
    sm_cards = board_cards.get("social-media", [])
    post_plan_list_id = "6994f47ba1999608d5cc1726"

    dated_tasks = []
    tbc_tasks = []
    for card in sm_cards:
        if card.get("idList") != post_plan_list_id:
            continue
        name = card.get("name", "")
        due = card.get("due")
        last_activity = card.get("dateLastActivity")
        short_url = f"https://trello.com/c/{card.get('shortLink', card.get('id', ''))}"
        labels_raw = card.get("labels", [])
        label_list = []
        for lb in labels_raw:
            ln = (lb.get("name") or "").strip().lower()
            if "feed" in ln:
                label_list.append("feed")
            elif "stories" in ln:
                label_list.append("stories")

        activity_str = format_date_pt(last_activity) if last_activity else ""

        if due:
            dt = datetime.fromisoformat(due.replace("Z", "+00:00")).astimezone(LISBON)
            date_str = f"{dt.year}-{dt.month:02d}-{dt.day:02d}"
            dated_tasks.append({
                "name": esc(name),
                "date": date_str,
                "labels": label_list,
                "activity": activity_str,
                "trello": short_url,
            })
        else:
            tbc_tasks.append({
                "name": esc(name),
                "activity": activity_str,
                "trello": short_url,
            })

    dated_tasks.sort(key=lambda t: t["date"])
    return dated_tasks, tbc_tasks


def render_calendar_js(dated_tasks, tbc_tasks):
    """Generate the JS block that builds the calendar and popup."""
    # Serialize task data to JS
    dated_js = json.dumps(dated_tasks, ensure_ascii=False)
    tbc_js = json.dumps(tbc_tasks, ensure_ascii=False)

    # Determine month range
    if dated_tasks:
        first_date = dated_tasks[0]["date"]
        last_date = dated_tasks[-1]["date"]
        start_year, start_month = int(first_date[:4]), int(first_date[5:7]) - 1
        end_year, end_month = int(last_date[:4]), int(last_date[5:7]) - 1
    else:
        start_year, start_month = 2026, 2
        end_year, end_month = 2026, 7

    months_array = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        months_array.append(f"[{y},{m}]")
        m += 1
        if m > 11:
            m = 0
            y += 1

    return f"""
(function(){{
  var postPlanTasks = {dated_js};
  var tbcTasks = {tbc_js};

  var today = new Date();
  today.setHours(0,0,0,0);
  var monthNames = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
  var weekdays = ['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'];

  var tasksByDate = {{}};
  postPlanTasks.forEach(function(t){{
    if(!tasksByDate[t.date]) tasksByDate[t.date]=[];
    tasksByDate[t.date].push(t);
  }});

  function getStatus(dateStr){{
    var d = new Date(dateStr+'T00:00:00');
    var diff = (d - today)/(1000*60*60*24);
    if(diff < 0) return 'overdue';
    if(diff <= 7) return 'upcoming';
    return 'future';
  }}

  function buildMonth(year, month){{
    var container = document.createElement('div');
    container.className = 'cal-month';
    var title = document.createElement('div');
    title.className = 'cal-month-name';
    title.textContent = monthNames[month] + ' ' + year;
    container.appendChild(title);
    var grid = document.createElement('div');
    grid.className = 'cal-grid';
    weekdays.forEach(function(wd){{
      var wdEl = document.createElement('div');
      wdEl.className = 'cal-weekday';
      wdEl.textContent = wd;
      grid.appendChild(wdEl);
    }});
    var firstDay = new Date(year, month, 1);
    var startOffset = (firstDay.getDay() + 6) % 7;
    var daysInMonth = new Date(year, month + 1, 0).getDate();
    for(var i=0; i<startOffset; i++){{
      var empty = document.createElement('div');
      empty.className = 'cal-day cal-empty';
      grid.appendChild(empty);
    }}
    var hasEvents = false;
    for(var d=1; d<=daysInMonth; d++){{
      var dayEl = document.createElement('div');
      dayEl.className = 'cal-day';
      var mm = String(month+1).padStart(2,'0');
      var dd = String(d).padStart(2,'0');
      var dateKey = year+'-'+mm+'-'+dd;
      var cellDate = new Date(year, month, d);
      if(cellDate.getTime() === today.getTime()) dayEl.classList.add('cal-today');
      var numEl = document.createElement('div');
      numEl.className = 'cal-day-num';
      numEl.textContent = d;
      dayEl.appendChild(numEl);
      if(tasksByDate[dateKey]){{
        hasEvents = true;
        tasksByDate[dateKey].forEach(function(task){{
          var evtEl = document.createElement('div');
          evtEl.className = 'cal-event evt-' + getStatus(task.date);
          evtEl.onclick = function(e){{e.stopPropagation();openPopup(task)}};
          var nameSpan = document.createElement('span');
          nameSpan.textContent = task.name;
          evtEl.appendChild(nameSpan);
          if(task.labels.length > 0){{
            var lbls = document.createElement('div');
            lbls.className = 'cal-event-labels';
            task.labels.forEach(function(l){{
              var lbl = document.createElement('span');
              lbl.className = 'cal-event-label lbl-' + l;
              lbl.textContent = l === 'feed' ? 'Feed' : 'Stories';
              lbls.appendChild(lbl);
            }});
            evtEl.appendChild(lbls);
          }}
          dayEl.appendChild(evtEl);
        }});
      }}
      grid.appendChild(dayEl);
    }}
    container.appendChild(grid);
    return hasEvents ? container : null;
  }}

  var monthsContainer = document.getElementById('cal-months-container');
  var months = [{",".join(months_array)}];
  months.forEach(function(ym){{
    var el = buildMonth(ym[0], ym[1]);
    if(el) monthsContainer.appendChild(el);
  }});

  var tbcSection = document.getElementById('cal-tbc-section');
  if(tbcTasks.length > 0){{
    var tbcTitle = document.createElement('div');
    tbcTitle.className = 'cal-tbc-title';
    tbcTitle.textContent = 'Sem Data Definida (TBC)';
    tbcSection.appendChild(tbcTitle);
    var tbcList = document.createElement('div');
    tbcList.className = 'cal-tbc-list';
    tbcTasks.forEach(function(task){{
      var item = document.createElement('div');
      item.className = 'cal-tbc-item';
      item.textContent = task.name;
      item.style.cursor = 'pointer';
      item.onclick = function(){{openPopup({{name:task.name,date:null,labels:[],activity:task.activity,trello:task.trello}})}};
      tbcList.appendChild(item);
    }});
    tbcSection.appendChild(tbcList);
  }}

  var statusLabels = {{overdue:'Atrasado',upcoming:'Próximo',future:'Futuro',tbc:'Sem Data'}};
  var monthNamesShort = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
  function formatDate(dateStr){{
    var parts = dateStr.split('-');
    return parseInt(parts[2],10)+' '+monthNamesShort[parseInt(parts[1],10)-1]+' '+parts[0];
  }}
  window.openPopup = function(task){{
    var overlay = document.getElementById('cal-overlay');
    var title = document.getElementById('popup-title');
    var body = document.getElementById('popup-body');
    var footer = document.getElementById('popup-footer');
    title.textContent = task.name;
    var status = task.date ? getStatus(task.date) : 'tbc';
    var html = '';
    html += '<div class="cal-popup-row"><span class="cal-popup-label">Data</span><span class="cal-popup-value">'+(task.date ? formatDate(task.date) : 'A definir')+'</span></div>';
    html += '<div class="cal-popup-row"><span class="cal-popup-label">Estado</span><span class="cal-popup-status st-'+status+'">'+statusLabels[status]+'</span></div>';
    if(task.labels && task.labels.length > 0){{
      html += '<div class="cal-popup-row"><span class="cal-popup-label">Tipo</span><div class="cal-popup-labels">';
      task.labels.forEach(function(l){{
        html += '<span class="cal-popup-lbl pl-'+l+'">'+(l==='feed'?'Post Feed':'Post Stories')+'</span>';
      }});
      html += '</div></div>';
    }}
    if(task.activity){{
      html += '<div class="cal-popup-row"><span class="cal-popup-label">Atividade</span><span class="cal-popup-value">'+task.activity+'</span></div>';
    }}
    body.innerHTML = html;
    footer.innerHTML = task.trello ? '<a href="'+task.trello+'" target="_blank" class="cal-popup-trello">Abrir no Trello &rarr;</a>' : '';
    overlay.classList.add('visible');
    document.addEventListener('keydown', escHandler);
  }};
  function escHandler(e){{if(e.key==='Escape')closePopup()}}
  window.closePopup = function(){{
    document.getElementById('cal-overlay').classList.remove('visible');
    document.removeEventListener('keydown', escHandler);
  }};
}})();
"""


def generate_html():
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    # Fetch all boards
    board_cards = {}
    board_totals = {}
    for key in BOARDS:
        cards = fetch_board_data(key)
        board_cards[key] = cards
        board_totals[key] = len(cards)

    # Build calendar data from Post Plan
    cal_dated, cal_tbc = build_calendar_data(board_cards)
    cal_total = len(cal_dated) + len(cal_tbc)

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
.cal-legend{{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:24px}}
.cal-legend-item{{display:flex;align-items:center;gap:6px;font-family:'Courier Prime',monospace;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}
.cal-legend-dot{{width:10px;height:10px;border-radius:2px}}
.cal-legend-dot.dot-overdue{{background:var(--red)}}
.cal-legend-dot.dot-upcoming{{background:var(--gold)}}
.cal-legend-dot.dot-future{{background:var(--green)}}
.cal-legend-dot.dot-tbc{{background:var(--muted)}}
.cal-months{{display:flex;flex-direction:column;gap:40px}}
.cal-month{{background:var(--surface);border:1px solid var(--border);padding:24px}}
.cal-month-name{{font-family:'Barlow Condensed',sans-serif;font-size:22px;font-weight:800;color:var(--gold);text-transform:uppercase;letter-spacing:.06em;margin-bottom:16px}}
.cal-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}}
.cal-weekday{{font-family:'Courier Prime',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);text-align:center;padding:8px 4px;border-bottom:1px solid var(--border)}}
.cal-day{{min-height:80px;padding:8px;background:var(--card);border:1px solid transparent;position:relative;transition:border-color .2s}}
.cal-day:hover{{border-color:var(--border)}}
.cal-day.cal-empty{{background:transparent;min-height:0}}
.cal-day-num{{font-family:'Courier Prime',monospace;font-size:12px;color:var(--muted);margin-bottom:6px;letter-spacing:.06em}}
.cal-day.cal-today{{border-color:var(--gold)}}
.cal-day.cal-today .cal-day-num{{color:var(--gold);font-weight:700}}
.cal-event{{font-family:'Barlow Condensed',sans-serif;font-size:12px;font-weight:600;padding:3px 6px;margin-bottom:2px;border-radius:2px;line-height:1.3;cursor:pointer;position:relative}}
.cal-event.evt-overdue{{background:rgba(196,55,58,.2);color:var(--red);border-left:2px solid var(--red)}}
.cal-event.evt-upcoming{{background:rgba(200,169,106,.2);color:var(--gold);border-left:2px solid var(--gold)}}
.cal-event.evt-future{{background:rgba(74,140,92,.15);color:var(--green);border-left:2px solid var(--green)}}
.cal-event-labels{{display:flex;gap:3px;margin-top:2px}}
.cal-event-label{{font-family:'Courier Prime',monospace;font-size:8px;letter-spacing:.06em;text-transform:uppercase;padding:1px 4px;border-radius:1px}}
.cal-event-label.lbl-feed{{background:rgba(200,169,106,.15);color:var(--gold)}}
.cal-event-label.lbl-stories{{background:rgba(74,140,92,.15);color:var(--green)}}
.cal-tbc-section{{margin-top:32px;background:var(--surface);border:1px solid var(--border);padding:24px}}
.cal-tbc-title{{font-family:'Barlow Condensed',sans-serif;font-size:18px;font-weight:800;color:var(--red);text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px}}
.cal-tbc-list{{display:flex;flex-wrap:wrap;gap:8px}}
.cal-tbc-item{{font-family:'Barlow Condensed',sans-serif;font-size:14px;font-weight:600;padding:6px 14px;background:rgba(196,55,58,.1);color:var(--red);border:1px solid rgba(196,55,58,.3);border-radius:2px;cursor:pointer}}
.cal-overlay{{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.7);z-index:1000;align-items:center;justify-content:center}}
.cal-overlay.visible{{display:flex}}
.cal-popup{{background:var(--card);border:1px solid var(--border);max-width:440px;width:90%;position:relative;animation:calPopIn .15s ease-out}}
@keyframes calPopIn{{from{{opacity:0;transform:scale(.95)}}to{{opacity:1;transform:scale(1)}}}}
.cal-popup-header{{padding:20px 24px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:flex-start;gap:12px}}
.cal-popup-title{{font-family:'Barlow Condensed',sans-serif;font-size:22px;font-weight:800;color:var(--cream);text-transform:uppercase;letter-spacing:.03em;line-height:1.3}}
.cal-popup-close{{background:none;border:1px solid var(--border);color:var(--muted);font-size:18px;cursor:pointer;width:32px;height:32px;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all .2s;font-family:'Courier Prime',monospace}}
.cal-popup-close:hover{{color:var(--cream);border-color:var(--cream)}}
.cal-popup-body{{padding:24px}}
.cal-popup-row{{display:flex;align-items:center;gap:12px;margin-bottom:14px}}
.cal-popup-row:last-child{{margin-bottom:0}}
.cal-popup-label{{font-family:'Courier Prime',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);min-width:90px}}
.cal-popup-value{{font-family:'Barlow',sans-serif;font-size:14px;color:var(--cream)}}
.cal-popup-status{{font-family:'Courier Prime',monospace;font-size:11px;letter-spacing:.08em;text-transform:uppercase;padding:3px 10px;border-radius:2px}}
.cal-popup-status.st-overdue{{background:rgba(196,55,58,.2);color:var(--red);border:1px solid var(--red)}}
.cal-popup-status.st-upcoming{{background:rgba(200,169,106,.2);color:var(--gold);border:1px solid var(--gold)}}
.cal-popup-status.st-future{{background:rgba(74,140,92,.15);color:var(--green);border:1px solid var(--green)}}
.cal-popup-status.st-tbc{{background:rgba(90,86,80,.2);color:var(--muted);border:1px solid var(--muted)}}
.cal-popup-labels{{display:flex;gap:6px;flex-wrap:wrap}}
.cal-popup-lbl{{font-family:'Courier Prime',monospace;font-size:10px;padding:3px 8px;letter-spacing:.08em;text-transform:uppercase;border-radius:2px}}
.cal-popup-lbl.pl-feed{{background:rgba(200,169,106,.2);color:var(--gold)}}
.cal-popup-lbl.pl-stories{{background:rgba(74,140,92,.2);color:var(--green)}}
.cal-popup-footer{{padding:16px 24px;border-top:1px solid var(--border)}}
.cal-popup-trello{{display:inline-block;font-family:'Courier Prime',monospace;font-size:11px;color:var(--gold);text-decoration:none;letter-spacing:.08em;text-transform:uppercase;border:1px solid var(--gold);padding:8px 16px;transition:all .2s;width:100%;text-align:center;box-sizing:border-box}}
.cal-popup-trello:hover{{background:var(--gold);color:var(--bg)}}
@media(max-width:768px){{.cal-grid{{grid-template-columns:repeat(7,1fr)}}.cal-day{{min-height:60px;padding:4px}}.cal-event{{font-size:10px;padding:2px 4px}}}}
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

    html += f'    <div class="board-tab" onclick="showBoard(\'calendario-posts\')">Calendário Post Plan<span class="tab-count">{cal_total} posts</span></div>\n'
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

    # Calendar overlay (popup)
    html += """  <div class="cal-overlay" id="cal-overlay" onclick="if(event.target===this)closePopup()">
    <div class="cal-popup">
      <div class="cal-popup-header">
        <div class="cal-popup-title" id="popup-title"></div>
        <button class="cal-popup-close" onclick="closePopup()">&times;</button>
      </div>
      <div class="cal-popup-body" id="popup-body"></div>
      <div class="cal-popup-footer" id="popup-footer"></div>
    </div>
  </div>

  <div id="calendario-posts" class="board-content">
    <div class="cal-legend">
      <div class="cal-legend-item"><div class="cal-legend-dot dot-overdue"></div>Atrasado</div>
      <div class="cal-legend-item"><div class="cal-legend-dot dot-upcoming"></div>Próximo</div>
      <div class="cal-legend-item"><div class="cal-legend-dot dot-future"></div>Futuro</div>
      <div class="cal-legend-item"><div class="cal-legend-dot dot-tbc"></div>Sem data</div>
    </div>
    <div class="cal-months" id="cal-months-container"></div>
    <div class="cal-tbc-section" id="cal-tbc-section"></div>
  </div>

"""

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
"""

    # Add calendar JS
    html += render_calendar_js(cal_dated, cal_tbc)

    html += """</script>
</body>
</html>"""

    return html


if __name__ == "__main__":
    html = generate_html()
    with open("tarefas.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("tarefas.html generated successfully")
