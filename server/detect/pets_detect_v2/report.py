"""Static HTML reports (HTML + CSS only, no JavaScript) for the v1/v2 comparison and the span detector.

Privacy: reports never print raw data values. Reasons are passed through `sanitize()`, which replaces quoted
values and anything that looks like an identifier with its masked shape ('070889-9652' -> '9x6-9x4').
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pandas as pd

from pets_detect.patterns import ROLES
from pets_detect.profiler import mask_shape

ROLE_SHORT = {"direct_identifier": "direct", "quasi_identifier": "quasi", "sensitive_attribute": "sensitive",
              "technical_identifier": "technical", "free_text": "free text", "record_key": "record key",
              "non_sensitive": "non-sensitive"}
VERSION_LABEL = {"v1": "v1 · session \"Read challenge\"", "v2": "v2 · this work"}
VERSION_DESC = {
    "v1": "Rules + regex (tier 1) → kNN retrieval over labelled columns (tier 2) → local LLM per column (tier 3).",
    "v2": "Same rules (tier 1) → logistic-regression column classifier (tier 2) → recall bias → local LLM with "
          "table context (tier 3: one call per table for its domain, one short call per unsure column) → guardrail.",
}

CSS = """
:root{--bg:#f6f7f9;--surface:#fff;--surface2:#f0f2f5;--text:#1b1f24;--muted:#5d6672;--border:#dde1e6;
--accent:#2457c5;--good:#1a7f37;--good-bg:#e6f4ea;--bad:#c62828;--bad-bg:#fdecea;--warn:#9a6700;
--r-direct:#c62828;--r-quasi:#c76a00;--r-sensitive:#7b3fb8;--r-technical:#1f6fd1;--r-free:#0f8a7e;
--r-key:#6b7280;--r-non:#4b7f52;--bar:#2457c5;--bar2:#9db4e8;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0f1216;--surface:#171b21;
--surface2:#1f242c;--text:#e6e9ee;--muted:#9aa3ae;--border:#2c333d;--accent:#7aa2ff;--good:#56c271;
--good-bg:#173323;--bad:#ff7b72;--bad-bg:#3a1d1d;--warn:#e3b341;--r-direct:#ff7b72;--r-quasi:#f0a35a;
--r-sensitive:#c49bff;--r-technical:#79b8ff;--r-free:#4fd1c5;--r-key:#9aa3ae;--r-non:#8ccf94;--bar:#7aa2ff;
--bar2:#3b4f80;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0f1216;--surface:#171b21;--surface2:#1f242c;--text:#e6e9ee;--muted:#9aa3ae;
--border:#2c333d;--accent:#7aa2ff;--good:#56c271;--good-bg:#173323;--bad:#ff7b72;--bad-bg:#3a1d1d;--warn:#e3b341;
--r-direct:#ff7b72;--r-quasi:#f0a35a;--r-sensitive:#c49bff;--r-technical:#79b8ff;--r-free:#4fd1c5;--r-key:#9aa3ae;
--r-non:#8ccf94;--bar:#7aa2ff;--bar2:#3b4f80;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",
Roboto,Helvetica,Arial,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 64px}
a{color:var(--accent)}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 12px}h3{font-size:15px;margin:20px 0 8px}
.sub{color:var(--muted);margin:0 0 16px}
nav.top{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;font-size:13px}
nav.top a{text-decoration:none;padding:4px 10px;border:1px solid var(--border);border-radius:999px;
background:var(--surface)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;margin:12px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.kpi .l{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.kpi .v{font-size:26px;font-weight:650;font-variant-numeric:tabular-nums}
.kpi .s{color:var(--muted);font-size:12px}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--border);vertical-align:top}
th{font-size:12px;color:var(--muted);font-weight:600;background:var(--surface2);position:sticky;top:0}
td.num,th.num{text-align:right}
tr.wrong td{background:var(--bad-bg)}
.badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600;
border:1px solid currentColor;white-space:nowrap}
.r-direct_identifier{color:var(--r-direct)}.r-quasi_identifier{color:var(--r-quasi)}
.r-sensitive_attribute{color:var(--r-sensitive)}.r-technical_identifier{color:var(--r-technical)}
.r-free_text{color:var(--r-free)}.r-record_key{color:var(--r-key)}.r-non_sensitive{color:var(--r-non)}
.ok{color:var(--good);font-weight:700}.ko{color:var(--bad);font-weight:700}
.up{color:var(--good);font-weight:600}.down{color:var(--bad);font-weight:600}.flat{color:var(--muted)}
.conf{display:inline-block;width:60px;height:6px;background:var(--surface2);border-radius:3px;
vertical-align:middle;margin-right:6px;overflow:hidden}.conf i{display:block;height:100%;background:var(--bar)}
.bars .row{display:grid;grid-template-columns:150px 1fr 52px;gap:8px;align-items:center;margin:5px 0}
.bars .track{height:10px;background:var(--surface2);border-radius:5px;overflow:hidden}
.bars .fill{height:100%;background:var(--bar)}.bars .fill.b2{background:var(--bar2)}
.legend{font-size:12px;color:var(--muted)}.legend i{display:inline-block;width:10px;height:10px;
border-radius:2px;margin:0 4px 0 10px;vertical-align:middle}
details{background:var(--surface);border:1px solid var(--border);border-radius:10px;margin:10px 0}
details>summary{cursor:pointer;padding:10px 14px;font-weight:600}
details>summary .meta{color:var(--muted);font-weight:400;margin-left:8px}
details .scroll{padding:0 6px 8px}
.reason{color:var(--muted);font-size:12.5px;max-width:460px}
.src{font-size:11.5px;color:var(--muted);white-space:nowrap}
.note{border-left:3px solid var(--accent);padding:8px 12px;background:var(--surface);border-radius:0 8px 8px 0;
color:var(--muted);margin:12px 0}
.winner{border:2px solid var(--good);background:var(--good-bg)}
.cm td{text-align:center;min-width:44px}.cm th.rowh{text-align:right}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}
.ex{background:var(--surface2);padding:6px 10px;border-radius:6px;margin:4px 0}
.ex mark{background:transparent;color:var(--accent);font-weight:600}
@media (max-width:640px){.bars .row{grid-template-columns:96px 1fr 44px}h1{font-size:20px}}
"""

_MASK_RX = re.compile(r"'([^']{1,80})'|\"([^\"]{1,80})\"|[\w.+\-]+@[\w.\-]+|\b(?=[\w@.+\-/,]*\d)[\w@.+\-/,]{4,}\b")
_KEEP_NUM = re.compile(r"\d{1,3}(?:[.,]\d+)?%?|[.,]\d+")


def sanitize(text: str) -> str:
    """Remove raw values from a reason in one pass: quoted strings and identifier-like tokens become masked
    shapes ('070889-9652' -> '9x6-9x4'); short numbers such as 95% or 0.53 are kept."""
    if not isinstance(text, str):
        return ""

    def rep(m):
        if m.group(1) is not None:
            return "'" + mask_shape(m.group(1)) + "'"
        if m.group(2) is not None:
            return '"' + mask_shape(m.group(2)) + '"'
        tok = m.group(0)
        core = tok.rstrip(".,")
        if _KEEP_NUM.fullmatch(core):
            return tok
        return mask_shape(core) + tok[len(core):]
    return _MASK_RX.sub(rep, text)


def e(x) -> str:
    return html.escape("" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x))


def badge(role: str) -> str:
    return f'<span class="badge r-{e(role)}">{e(ROLE_SHORT.get(role, role))}</span>'


def fmt(v, d=3) -> str:
    return "–" if v is None or (isinstance(v, float) and pd.isna(v)) else f"{v:.{d}f}"


def delta(a, b) -> str:
    if a is None or b is None:
        return '<span class="flat">–</span>'
    d = b - a
    cls = "up" if d > 0.0005 else "down" if d < -0.0005 else "flat"
    return f'<span class="{cls}">{d:+.3f}</span>'


def page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title>'
            f'<style>{CSS}</style></head><body><main>{body}</main></body></html>')


def kpis(items: list[tuple[str, str, str]]) -> str:
    return '<div class="grid">' + "".join(
        f'<div class="kpi"><div class="l">{e(l)}</div><div class="v">{v}</div><div class="s">{s}</div></div>'
        for l, v, s in items) + "</div>"


def role_bars(sc_blind: dict, sc_names: dict) -> str:
    rows = []
    for r in ROLES:
        a = sc_blind["per_role"][r]
        b = sc_names["per_role"][r]
        if a["support"] == 0:
            continue
        rows.append(
            f'<div class="row"><div>{badge(r)} <span class="src">n={a["support"]}</span></div>'
            f'<div><div class="track"><div class="fill" style="width:{100 * a["f1"]:.0f}%"></div></div>'
            f'<div class="track" style="margin-top:3px"><div class="fill b2" style="width:{100 * b["f1"]:.0f}%">'
            f'</div></div></div><div class="mono">{a["f1"]:.2f}<br>{b["f1"]:.2f}</div></div>')
    return ('<div class="legend">F1 per role:<i style="background:var(--bar)"></i>names hidden'
            '<i style="background:var(--bar2)"></i>with names</div><div class="bars">' + "".join(rows) + "</div>")


def confusion(sc: dict) -> str:
    cm = sc["confusion"]
    golds = [r for r in ROLES if any(r in cm.get(p, {}) for p in cm)]
    preds = [r for r in ROLES + ["missing"] if r in cm]
    mx = max([v for p in cm.values() for v in p.values()] or [1])
    head = "".join(f"<th>{badge(p) if p in ROLES else e(p)}</th>" for p in preds)
    body = ""
    for g in golds:
        cells = ""
        for p in preds:
            v = cm.get(p, {}).get(g, 0) or 0
            a = 0.08 + 0.6 * v / mx if v else 0
            col = "var(--good)" if p == g else "var(--bad)"
            style = f' style="background:color-mix(in srgb,{col} {a * 100:.0f}%,transparent)"' if v else ""
            cells += f"<td{style}>{int(v) if v else ''}</td>"
        body += f'<tr><th class="rowh">{badge(g)}</th>{cells}</tr>'
    return (f'<div class="scroll"><table class="cm"><tr><th>gold ↓ / predicted →</th>{head}</tr>{body}</table></div>')


def _truth(catalog: pd.DataFrame, ds: str) -> pd.DataFrame:
    return catalog[catalog.dataset == ds][["table", "column", "privacy_role", "subtype", "art9_special_category"]] \
        .rename(columns={"privacy_role": "gold_role", "subtype": "gold_subtype", "art9_special_category": "gold_art9"})


def dataset_page(ds: str, version: str, preds: dict[str, pd.DataFrame], summary: dict, catalog: pd.DataFrame,
                 other: str, linkage: dict | None = None) -> str:
    runs = summary["runs"]
    has_truth = ds in summary["labelled"]
    pb = preds["blind"][preds["blind"].dataset == ds].copy()
    pn = preds["names"][preds["names"].dataset == ds][["table", "column", "privacy_role", "subtype"]] \
        .rename(columns={"privacy_role": "names_role", "subtype": "names_subtype"})
    df = pb.merge(pn, on=["table", "column"], how="left")
    if has_truth:
        df = df.merge(_truth(catalog, ds), on=["table", "column"], how="left")
    rb, rn = runs[f"{version}_blind"], runs[f"{version}_names"]
    t_b, t_n = rb["times"].get(ds), rn["times"].get(ds)
    head = (f'<nav class="top"><a href="index.html">← all datasets</a><a href="{ds}_{other}.html">'
            f'same dataset, {other}</a></nav><h1>{e(ds)} · {e(VERSION_LABEL[version])}</h1>'
            f'<p class="sub">{e(VERSION_DESC[version])}</p>')
    meta = (f'<div class="card"><b>{df.table.nunique()}</b> tables · <b>{len(df)}</b> columns · LLM: '
            f'{e(rb.get("llm_model") or "off") if rb.get("llm") else "off"} · run time {fmt(t_b, 1)} s (names hidden), '
            f'{fmt(t_n, 1)} s (with names) · generated {e(summary["created"])}</div>')
    body = head + meta
    if has_truth:
        sb, sn = rb["per_dataset"][ds], rn["per_dataset"][ds]
        body += "<h2>Scores against the organisers' field catalog</h2>"
        body += ('<p class="sub">Leave-one-dataset-out: nothing learned from this dataset was used to label it. '
                 '"Names hidden" ignores column and table names, like the obfuscated <span class="mono">unseen</span> '
                 'export, and is the fairer number.</p>')
        body += kpis([
            ("macro-F1 · names hidden", fmt(sb["macro_f1"]), f'with names {fmt(sn["macro_f1"])}'),
            ("accuracy · names hidden", fmt(sb["accuracy"]), f'with names {fmt(sn["accuracy"])}'),
            ("sensitive recall · names hidden", fmt(sb["sensitive_recall"]),
             f'with names {fmt(sn["sensitive_recall"])}'),
            ("subtype accuracy · names hidden", fmt(sb.get("subtype_accuracy")),
             f'with names {fmt(sn.get("subtype_accuracy"))}'),
        ])
        body += f'<div class="card">{role_bars(sb, sn)}</div>'
        body += f'<h3>Confusion matrix (names hidden)</h3><div class="card">{confusion(sb)}</div>'
    else:
        body += ('<div class="note">No public ground truth for this dataset: the organisers keep the labels. '
                 'Only the predictions and their reasons are shown.</div>')
    body += "<h2>Every column</h2>"
    body += ('<p class="sub">Main prediction = names hidden. Red rows are wrong against the catalog. '
             'Reasons are shown with values masked (e.g. <span class="mono">9x6-9x4</span>).</p>')
    for table, g in df.groupby("table", sort=False):
        n_wrong = int((g.privacy_role != g.gold_role).sum()) if has_truth else 0
        dom = g["table_domain"].dropna().astype(str) if "table_domain" in g else []
        dom = next((x for x in dom if x), "")
        rows = ""
        for _, r in g.iterrows():
            wrong = has_truth and r.privacy_role != r.gold_role
            conf = float(r.get("confidence", 0) or 0)
            gold = ""
            if has_truth:
                gold = (f'<td>{badge(r.gold_role)}<div class="src">{e(r.gold_subtype)}</div></td>'
                        f'<td>{"<span class=ko>✗</span>" if wrong else "<span class=ok>✓</span>"}</td>')
            extra = ""
            if str(r.get("needs_review", "")) == "True":
                extra += ' <span class="src" style="color:var(--warn)">needs review</span>'
            if "art9" in r and str(r.get("art9")) == "True":
                extra += ' <span class="src" style="color:var(--r-sensitive)">Art. 9</span>'
            rows += (f'<tr class="{"wrong" if wrong else ""}"><td class="mono">{e(r.column)}</td>'
                     f'<td>{badge(r.privacy_role)}{extra}<div class="src">{e(r.subtype)}</div></td>'
                     f'<td>{badge(r.names_role) if isinstance(r.names_role, str) else ""}</td>{gold}'
                     f'<td class="src"><span class="conf"><i style="width:{100 * conf:.0f}%"></i></span>'
                     f'{conf:.2f}</td><td class="src">{e(r.get("source", ""))}</td>'
                     f'<td class="reason">{e(sanitize(r.get("reason", "")))}</td></tr>')
        th_gold = "<th>catalog</th><th></th>" if has_truth else ""
        summ = f'{e(table)}<span class="meta">{len(g)} columns'
        summ += f' · <span class="{"ko" if n_wrong else "ok"}">{n_wrong} wrong</span>' if has_truth else ""
        summ += f" · domain: {e(sanitize(dom))}" if dom else ""
        summ += "</span>"
        body += (f'<details open><summary>{summ}</summary><div class="scroll"><table><tr><th>column</th>'
                 f'<th>predicted (names hidden)</th><th>with names</th>{th_gold}<th>confidence</th><th>decided by</th>'
                 f'<th>reason</th></tr>{rows}</table></div></details>')
    if has_truth:
        w = df[df.privacy_role != df.gold_role]
        body += f"<h2>Wrong predictions ({len(w)})</h2>"
        if len(w):
            rows = "".join(f'<tr><td class="mono">{e(r.table)}.{e(r.column)}</td><td>{badge(r.gold_role)}</td>'
                           f'<td>{badge(r.privacy_role)}</td><td class="src">{e(r.get("source", ""))}</td></tr>'
                           for _, r in w.iterrows())
            body += (f'<div class="card scroll"><table><tr><th>column</th><th>catalog</th><th>predicted</th>'
                     f'<th>decided by</th></tr>{rows}</table></div>')
        else:
            body += '<p class="ok">None.</p>'
    if linkage:
        body += linkage_html(linkage)
    return page(f"{ds} {version}", body)


def _overall_row(name: str, sb: dict | None, sn: dict | None) -> str:
    def c(s, k):
        return fmt(s.get(k)) if s else "–"
    sa = lambda s: fmt(s["per_role"]["sensitive_attribute"]["f1"]) if s else "–"
    return (f"<tr><td>{name}</td><td class=num>{c(sb, 'macro_f1')}</td><td class=num>{c(sb, 'sensitive_recall')}</td>"
            f"<td class=num>{sa(sb)}</td><td class=num>{c(sb, 'subtype_accuracy')}</td>"
            f"<td class=num>{c(sn, 'macro_f1')}</td><td class=num>{c(sn, 'sensitive_recall')}</td>"
            f"<td class=num>{sa(sn)}</td></tr>")


def pick_winner(summary: dict) -> tuple[str, str]:
    runs = summary["runs"]
    if "overall" not in runs.get("v1_blind", {}):
        return "", "no labelled dataset was run"
    a, b = runs["v1_blind"]["overall"], runs["v2_blind"]["overall"]
    if abs(a["macro_f1"] - b["macro_f1"]) >= 0.01:
        w = "v2" if b["macro_f1"] > a["macro_f1"] else "v1"
        why = (f"macro-F1 with names hidden: v1 {a['macro_f1']:.3f} vs v2 {b['macro_f1']:.3f} "
               f"(difference ≥ 0.01, criterion 1)")
    else:
        w = "v2" if b["sensitive_recall"] >= a["sensitive_recall"] else "v1"
        why = (f"macro-F1 within 0.01 ({a['macro_f1']:.3f} vs {b['macro_f1']:.3f}); sensitive recall decides: "
               f"v1 {a['sensitive_recall']:.3f} vs v2 {b['sensitive_recall']:.3f} (criterion 2)")
    return w, why


def index_page(summary: dict, ablation: pd.DataFrame | None, spans: dict | None) -> str:
    runs = summary["runs"]
    w, why = pick_winner(summary)
    body = ('<h1>Detect: v1 vs v2</h1><p class="sub">Column-level privacy-role detection on the TRUSTED PETs '
            f'Proving Ground datasets. Generated {e(summary["created"])}. Pure HTML/CSS, no data values shown.</p>')
    body += ('<div class="card"><b>Protocol.</b> Both versions run on the same column profiles, the same local LLM '
             f'({e(runs["v2_blind"].get("llm_model") or "off")}, temperature 0) and are scored with '
             '<span class="mono">pets_eval.detect.score_detection</span> against '
             '<span class="mono">metadata/field_catalog.csv</span>, leave-one-dataset-out. '
             '<br><b>v1</b>: ' + e(VERSION_DESC["v1"]) + '<br><b>v2</b>: ' + e(VERSION_DESC["v2"]) + "</div>")
    if w:
        body += (f'<div class="card winner"><b>Base for step 7: {e(VERSION_LABEL[w])}</b><br>{e(why)}.'
                 '<br><span class="src">Criteria, in order: 1) macro-F1 with names hidden, 2) sensitive recall '
                 'with names hidden, 3) eyeball check on unseen.</span></div>')
    body += "<h2>Overall (labelled datasets)</h2>"
    rows = _overall_row("B1 baseline (organisers, uses names)", None, summary.get("b1"))
    for v in ("v1", "v2"):
        rows += _overall_row(e(VERSION_LABEL[v]), runs[f"{v}_blind"].get("overall"), runs[f"{v}_names"].get("overall"))
    body += ('<div class="card scroll"><table><tr><th></th><th class=num colspan=4>names hidden</th>'
             '<th class=num colspan=3>with names</th></tr><tr><th>version</th><th class=num>macro-F1</th>'
             '<th class=num>sensitive recall</th><th class=num>F1 sensitive attr.</th><th class=num>subtype acc.</th>'
             '<th class=num>macro-F1</th><th class=num>sensitive recall</th><th class=num>F1 sensitive attr.</th></tr>'
             f'{rows}</table></div>')
    body += "<h2>Per dataset</h2>"
    rows = ""
    for ds in summary["datasets"]:
        lab = ds in summary["labelled"]
        g = lambda v, m: runs[f"{v}_{m}"]["per_dataset"].get(ds, {}).get("macro_f1") if lab else None
        t = lambda v: sum(x for x in (runs[f"{v}_blind"]["times"].get(ds), runs[f"{v}_names"]["times"].get(ds)) if x)
        rows += (f'<tr><td><b>{e(ds)}</b>{"" if lab else " <span class=src>(no public labels)</span>"}</td>'
                 f'<td class=num>{fmt(g("v1", "blind"))}</td><td class=num>{fmt(g("v2", "blind"))}</td>'
                 f'<td class=num>{delta(g("v1", "blind"), g("v2", "blind"))}</td>'
                 f'<td class=num>{fmt(g("v1", "names"))}</td><td class=num>{fmt(g("v2", "names"))}</td>'
                 f'<td class=num>{delta(g("v1", "names"), g("v2", "names"))}</td>'
                 f'<td class=num>{t("v1"):.0f} s / {t("v2"):.0f} s</td>'
                 f'<td><a href="{ds}_v1.html">v1</a> · <a href="{ds}_v2.html">v2</a>'
                 + (f' · <a href="{ds}_spans.html">spans</a>' if spans and ds in spans.get("datasets", {}) else "")
                 + "</td></tr>")
    body += ('<div class="card scroll"><table><tr><th>dataset</th><th class=num>v1 F1<br>hidden</th>'
             '<th class=num>v2 F1<br>hidden</th><th class=num>Δ</th><th class=num>v1 F1<br>names</th>'
             '<th class=num>v2 F1<br>names</th><th class=num>Δ</th><th class=num>run time*<br>v1 / v2</th>'
             f'<th>reports</th></tr>{rows}</table></div>'
             '<p class="src">* Both modes, with cached LLM answers, so these times are not the cost of a first run. '
             'A first, uncached v2 run of all datasets in both modes took about 15 minutes on an M4 Pro '
             '(226 LLM calls). v1\'s LLM answers were already cached by an earlier v1 evaluation.</p>')
    if ablation is not None and len(ablation):
        body += "<h2>v2 ablation (no LLM)</h2>"
        body += ('<p class="sub">How the tier-2 model and the recall-bias margin were chosen. Same leave-one-dataset-out '
                 'protocol, tiers 1–2 only.</p>')
        cols = [c for c in ablation.columns]
        th = "".join(f"<th{' class=num' if ablation[c].dtype != object else ''}>{e(c)}</th>" for c in cols)
        tr = "".join("<tr>" + "".join(
            f"<td class=num>{v:.3f}</td>" if isinstance(v, float) else f"<td>{e(v)}</td>" for v in r) + "</tr>"
            for r in ablation.itertuples(index=False))
        body += f'<div class="card scroll"><table><tr>{th}</tr>{tr}</table></div>'
    if spans:
        body += span_summary_html(spans)
    body += ('<h2>Caveats</h2><div class="note">The tier-1 name rules of both versions were written after reading the '
             'catalog, so "with names" scores are optimistic. Names-hidden scores and the organisers\' private labels '
             'for <span class="mono">unseen</span> are the honest test. LLM answers depend on the model version; '
             'they are cached so the reports are reproducible.</div>')
    return page("Detect v1 vs v2", body)


def linkage_html(res: dict) -> str:
    out = ('<h2>Linkage facts for the Select step</h2><p class="sub">Computed from the data with this version\'s '
           'column labels. Counts and column names only.</p>')
    if res.get("qi_risk"):
        rows = ""
        for q in res["qi_risk"]:
            drop = ", ".join(f"{e(c)} → {v:.0%}" for c, v in sorted(q["drop_one_share_k_lt5"].items(),
                                                                    key=lambda x: x[1])[:3])
            rows += (f'<tr><td class="mono">{e(q["table"])}</td><td>{e(", ".join(q["quasi_identifiers"]))}</td>'
                     f'<td class=num>{q["share_rows_k_lt5_raw"]:.0%}</td><td class=num>{q["share_rows_k_lt5_coarsened"]:.0%}</td>'
                     f'<td class="mono">{e(q["most_identifying_column"])}</td><td class="src">{drop}</td></tr>')
        out += ('<h3>Rows in groups smaller than k=5 on the detected quasi-identifiers</h3>'
                '<div class="card scroll"><table><tr><th>table</th><th>quasi-identifiers</th><th class=num>raw</th>'
                '<th class=num>after default coarsening</th><th>most identifying column</th>'
                '<th>share k&lt;5 if that column is dropped</th></tr>' + rows + "</table></div>"
                '<p class="src">Default coarsening: dates → month, birth dates → year, age → 5-year band, '
                'postcode → 3 digits, GPS → 2 decimals.</p>')
    if res.get("join_keys"):
        rows = "".join(f'<tr><td class="mono">{e(j["column"])}</td><td class="mono">{e(", ".join(j["links_to"]))}</td>'
                       f'<td>{badge(j["role"])}</td></tr>' for j in res["join_keys"])
        out += ('<h3>Join keys (need one consistent pseudonym across tables)</h3><div class="card scroll"><table>'
                '<tr><th>column</th><th>links to</th><th>role</th></tr>' + rows + "</table></div>")
    if res.get("shared_identifiers"):
        rows = "".join(f'<tr><td class="mono">{e(x["column"])}</td><td>{e(x["subtype"])}</td>'
                       f'<td class="mono">{e(x["also_in"])}</td><td class=num>{x["shared_values"]}</td>'
                       f'<td class=num>{x["share_of_column"]:.0%}</td></tr>' for x in res["shared_identifiers"])
        out += ('<h3>Identifiers that also appear in other datasets (cross-dataset linkage)</h3>'
                '<div class="card scroll"><table><tr><th>column</th><th>subtype</th><th>also in</th>'
                '<th class=num>shared values</th><th class=num>share of column</th></tr>' + rows + "</table></div>")
    if res.get("embedded"):
        rows = "".join(f'<tr><td class="mono">{e(x["column"])}</td><td>{e(x["subtype"])}</td>'
                       f'<td>{e("; ".join(x["reveals"]))}</td></tr>' for x in res["embedded"])
        out += ('<h3>Information hidden inside identifiers</h3><div class="card scroll"><table><tr><th>column</th>'
                '<th>subtype</th><th>reveals</th></tr>' + rows + "</table></div>")
    return out


def span_summary_html(spans: dict) -> str:
    rows = ""
    for key, s in spans["files"].items():
        b, v = s.get("b2", {}).get("micro", {}), s.get("v2", {}).get("micro", {})
        rows += (f'<tr><td class="mono">{e(key)}</td><td class=num>{s.get("n_test", 0)}</td>'
                 f'<td class=num>{fmt(b.get("recall"))}</td><td class=num>{fmt(v.get("recall"))}</td>'
                 f'<td class=num>{fmt(b.get("precision"))}</td><td class=num>{fmt(v.get("precision"))}</td>'
                 f'<td class=num>{fmt(b.get("f2"))}</td><td class=num>{fmt(v.get("f2"))}</td>'
                 f'<td class=num>{delta(b.get("f2"), v.get("f2"))}</td></tr>')
    return ('<h2>Step 7 · PII spans in free text</h2><p class="sub">' + e(spans.get("protocol", "")) + '</p>'
            '<div class="card scroll"><table><tr><th>text column</th><th class=num>test records</th>'
            '<th class=num>recall B2</th><th class=num>recall v2</th><th class=num>precision B2</th>'
            '<th class=num>precision v2</th><th class=num>F2 B2</th><th class=num>F2 v2</th><th class=num>Δ F2</th></tr>'
            f'{rows}</table></div>')


def prec(p: dict) -> str:
    """Precision is undefined (not 0) when a system predicted nothing for a label."""
    return fmt(p.get("precision")) if p.get("tp", 0) + p.get("fp", 0) else "–"


def span_page(ds: str, spans: dict) -> str:
    body = (f'<nav class="top"><a href="index.html">← all datasets</a><a href="{ds}_v1.html">columns v1</a>'
            f'<a href="{ds}_v2.html">columns v2</a></nav><h1>{e(ds)} · PII spans in free text</h1>'
            f'<p class="sub">{e(spans.get("protocol", ""))}</p>')
    for key, s in spans["files"].items():
        if not key.startswith(ds + "__"):
            continue
        body += f'<h2 class="mono">{e(key)}</h2>'
        b, v = s.get("b2", {}), s.get("v2", {})
        bm, vm = b.get("micro", {}), v.get("micro", {})
        body += kpis([
            ("recall", fmt(vm.get("recall")), f'B2 regex {fmt(bm.get("recall"))}'),
            ("precision", fmt(vm.get("precision")), f'B2 regex {fmt(bm.get("precision"))}'),
            ("F2 (recall-weighted)", fmt(vm.get("f2")), f'B2 regex {fmt(bm.get("f2"))}'),
            ("test records", str(s.get("n_test", 0)), f'{s.get("n_train", 0)} used for training'),
        ])
        labels = sorted(set(b.get("per_label", {})) | set(v.get("per_label", {})),
                        key=lambda l: -(v.get("per_label", {}).get(l, {}).get("tp", 0)
                                        + v.get("per_label", {}).get(l, {}).get("fn", 0)))
        rows = ""
        for l in labels:
            pb, pv = b.get("per_label", {}).get(l, {}), v.get("per_label", {}).get(l, {})
            gold = pv.get("tp", 0) + pv.get("fn", 0)
            if gold == 0 and not pv.get("fp"):
                continue
            rows += (f'<tr><td>{e(l)}</td><td class=num>{gold}</td><td class=num>{fmt(pb.get("recall"))}</td>'
                     f'<td class=num>{fmt(pv.get("recall"))}</td><td class=num>{delta(pb.get("recall"), pv.get("recall"))}</td>'
                     f'<td class=num>{prec(pb)}</td><td class=num>{prec(pv)}</td>'
                     f'<td class=num>{pv.get("fn", 0)}</td></tr>')
        body += ('<div class="card scroll"><table><tr><th>label</th><th class=num>gold spans</th>'
                 '<th class=num>recall B2</th><th class=num>recall v2</th><th class=num>Δ</th>'
                 '<th class=num>precision B2</th><th class=num>precision v2</th><th class=num>missed (v2)</th></tr>'
                 f'{rows}</table></div>')
        if s.get("examples"):
            body += "<h3>Examples (text with every detected span replaced by its label; no raw values)</h3>"
            body += "".join(f'<div class="ex">{x}</div>' for x in s["examples"])
    return page(f"{ds} spans", body)


def build(out_dir: Path, catalog: pd.DataFrame, compare_dir: Path = Path("out/compare"),
          spans_dir: Path = Path("out/spans")) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = json.loads((compare_dir / "summary.json").read_text())
    preds = {v: {m: pd.read_csv(compare_dir / f"pred_{v}_{m}.csv", dtype=str) for m in ("blind", "names")}
             for v in ("v1", "v2")}
    for v in preds:
        for m in preds[v]:
            preds[v][m]["confidence"] = pd.to_numeric(preds[v][m]["confidence"], errors="coerce")
    abl = pd.read_csv(compare_dir / "ablation.csv") if (compare_dir / "ablation.csv").exists() else None
    spans = json.loads((spans_dir / "summary.json").read_text()) if (spans_dir / "summary.json").exists() else None
    lk_dir = Path("out/linkage")
    lk_base = json.loads((lk_dir / "summary.json").read_text())["base"] if (lk_dir / "summary.json").exists() else None
    written = []
    for ds in summary["datasets"]:
        for v, o in (("v1", "v2"), ("v2", "v1")):
            lk = None
            if v == lk_base and (lk_dir / f"{ds}.json").exists():
                lk = json.loads((lk_dir / f"{ds}.json").read_text())
            f = out_dir / f"{ds}_{v}.html"
            f.write_text(dataset_page(ds, v, preds[v], summary, catalog, o, lk))
            written.append(f)
    if spans:
        for ds in spans.get("datasets", {}):
            f = out_dir / f"{ds}_spans.html"
            f.write_text(span_page(ds, spans))
            written.append(f)
    f = out_dir / "index.html"
    f.write_text(index_page(summary, abl, spans))
    written.append(f)
    return written
