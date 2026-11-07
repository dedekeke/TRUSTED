"""HTML reports for v3 (HTML + CSS only). v1/v2 pages in out/reports/ are linked, never regenerated."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pets_detect.patterns import ROLES
from pets_detect.pipeline import root_paths

from pets_detect_v2.report import (badge, confusion, delta, e, fmt, kpis, page, role_bars, sanitize)

from .compare import OUT, REPORTS

LABEL = {"v1": "v1 · session \"Read challenge\"", "v2": "v2", "v3": "v3 · router + fixes"}
DESC_V3 = ("Rules (tier 1) → per-column router: kNN on names when any name context exists (column or table name), "
           "logistic regression on values when there is none → recall bias (wider in Art. 9 person tables) → local "
           "LLM shown value distributions, with the table domain → guardrails; LLM may raise a column to sensitive "
           "only in Art. 9 tables → confidence from the statistical model, review flag when the model is unsure.")
TRACK = [("health", "ed_visits", c) for c in
         ("arrival_mode", "ambulance_unit", "triage", "temp_c", "disposition", "readmit_30d")]


def _sc(runs, v, m, ds=None):
    r = runs.get(f"{v}_{m}", {})
    return (r.get("per_dataset", {}).get(ds) if ds else r.get("overall"))


def pick(res: dict) -> tuple[str, str]:
    a, b = _sc(res["runs"], "v2", "blind"), _sc(res["runs"], "v3", "blind")
    an, bn = _sc(res["runs"], "v2", "names"), _sc(res["runs"], "v3", "names")
    if abs(a["macro_f1"] - b["macro_f1"]) >= .01:
        w = "v3" if b["macro_f1"] > a["macro_f1"] else "v2"
        why = f"macro-F1 names hidden: v2 {a['macro_f1']:.3f} vs v3 {b['macro_f1']:.3f}"
    else:
        w = "v3" if b["sensitive_recall"] >= a["sensitive_recall"] else "v2"
        why = (f"macro-F1 names hidden within 0.01 ({a['macro_f1']:.3f} vs {b['macro_f1']:.3f}); sensitive recall: "
               f"v2 {a['sensitive_recall']:.3f} vs v3 {b['sensitive_recall']:.3f}")
    why += f". With names: v1 {_sc(res['runs'], 'v1', 'names')['macro_f1']:.3f}, v2 {an['macro_f1']:.3f}, v3 {bn['macro_f1']:.3f}"
    return w, why


def table_html(df: pd.DataFrame, num_cols=()) -> str:
    th = "".join(f"<th{' class=num' if c in num_cols else ''}>{e(c)}</th>" for c in df.columns)
    tr = ""
    for r in df.itertuples(index=False):
        tr += "<tr>" + "".join(f"<td class=num>{v:.3f}</td>" if isinstance(v, float) else
                               f"<td class=num>{v}</td>" if isinstance(v, int) else f"<td>{e(v)}</td>" for v in r) + "</tr>"
    return f'<div class="card scroll"><table><tr>{th}</tr>{tr}</table></div>'


def index_page(res: dict, preds: dict) -> str:
    runs = res["runs"]
    w, why = pick(res)
    body = ('<nav class="top"><a href="../reports/index.html">v1 vs v2 report (earlier)</a></nav>'
            '<h1>Detect: v1 vs v2 vs v3</h1>'
            f'<p class="sub">Only v3 was run now ({e(res["created"])}). v1 and v2 numbers are re-scored from the saved '
            f'predictions of the earlier comparison ({e(res["baseline_created"])}), with the same scorer and catalog.</p>')
    body += f'<div class="card"><b>v3</b>: {e(DESC_V3)}</div>'
    body += (f'<div class="card winner"><b>Better of v2 / v3 (base for step 7): {e(LABEL[w])}</b><br>{e(why)}.</div>')
    rows = []
    for v in ("v1", "v2", "v3"):
        sb, sn = _sc(runs, v, "blind"), _sc(runs, v, "names")
        rows.append([LABEL[v], sb["macro_f1"], sb["sensitive_recall"], sb["per_role"]["sensitive_attribute"]["f1"],
                     sb.get("subtype_accuracy") or 0.0, sn["macro_f1"], sn["sensitive_recall"],
                     sn["per_role"]["sensitive_attribute"]["f1"]])
    df = pd.DataFrame(rows, columns=["version", "F1 hidden", "sens. recall hidden", "F1 sens. attr. hidden",
                                     "subtype acc. hidden", "F1 names", "sens. recall names", "F1 sens. attr. names"])
    body += "<h2>Overall (9 labelled datasets, leave-one-dataset-out)</h2>" + table_html(df, df.columns[1:])
    # per dataset
    body += "<h2>Per dataset (macro-F1)</h2>"
    tr = ""
    for ds in res["datasets"]:
        lab = ds in res["labelled"]
        g = lambda v, m: (_sc(runs, v, m, ds) or {}).get("macro_f1") if lab else None
        best = lambda m: max(x for x in (g("v1", m), g("v2", m)) if x is not None) if lab else None
        tr += (f'<tr><td><b>{e(ds)}</b></td>' + "".join(f"<td class=num>{fmt(g(v, 'blind'))}</td>" for v in ("v1", "v2", "v3"))
               + f"<td class=num>{delta(best('blind'), g('v3', 'blind'))}</td>"
               + "".join(f"<td class=num>{fmt(g(v, 'names'))}</td>" for v in ("v1", "v2", "v3"))
               + f"<td class=num>{delta(best('names'), g('v3', 'names'))}</td>"
               + f'<td><a href="../reports/{ds}_v1.html">v1</a> · <a href="../reports/{ds}_v2.html">v2</a> · '
               f'<a href="{ds}_v3.html">v3</a></td></tr>')
    body += ('<div class="card scroll"><table><tr><th>dataset</th><th class=num>v1<br>hidden</th><th class=num>v2<br>hidden</th>'
             '<th class=num>v3<br>hidden</th><th class=num>Δ v3 vs best<br>of v1/v2</th><th class=num>v1<br>names</th>'
             '<th class=num>v2<br>names</th><th class=num>v3<br>names</th><th class=num>Δ v3 vs best<br>of v1/v2</th>'
             f'<th>reports</th></tr>{tr}</table></div>')
    # tracked columns
    cat = res["_catalog"]
    tr = ""
    for ds, t, c in TRACK:
        gold = cat[(cat.dataset == ds) & (cat.table == t) & (cat.column == c)].privacy_role.iloc[0]
        cells = ""
        for v, m in (("v2", "blind"), ("v3", "blind"), ("v2", "names"), ("v3", "names")):
            p = preds[v][m]
            r = p[(p.dataset == ds) & (p.table == t) & (p.column == c)].iloc[0]
            ok = r.privacy_role == gold
            flag = ' <span class="src" style="color:var(--warn)">review</span>' if str(r.get("needs_review")) == "True" else ""
            cells += f'<td>{badge(r.privacy_role)} {"<span class=ok>✓</span>" if ok else "<span class=ko>✗</span>"}{flag}<div class="src">conf {float(r.confidence):.2f}</div></td>'
        tr += f'<tr><td class="mono">{e(c)}</td><td>{badge(gold)}</td>{cells}</tr>'
    body += ('<h2>The 6 columns analysed in health.ed_visits</h2><p class="sub">Wrong in v2 (names hidden). '
             '"review" = flagged needs_review for the Select step.</p><div class="card scroll"><table><tr><th>column</th>'
             '<th>catalog</th><th>v2 hidden</th><th>v3 hidden</th><th>v2 names</th><th>v3 names</th></tr>'
             f'{tr}</table></div>')
    # mixed
    if res.get("mixed"):
        df = pd.DataFrame([[k, v["macro_f1"], v["sensitive_recall"], v["per_role"]["sensitive_attribute"]["f1"]]
                           for k, v in res["mixed"].items()], columns=["tier 2", "macro-F1", "sensitive recall",
                                                                       "F1 sens. attr."])
        body += ('<h2>Mixed view: half of each table\'s column names hidden (no LLM)</h2><p class="sub">Checks the '
                 'per-column router. v1/v2 were never run in this view.</p>' + table_html(df, df.columns[1:]))
    for f, title, sub in ((OUT / "ablation.csv", "Ablation without LLM (steps 0–2)",
                           "Step 0 = v2 code. Router variants: knn / logreg / A1 switch / A2 blend."),
                          (OUT / "ablation_llm.csv", "Ablation with LLM (steps 4–5)",
                           "Each fix added on top of the previous one. Last column but one: wrong labels with "
                           "confidence ≥ 0.8 that are not flagged for review.")):
        if f.exists():
            df = pd.read_csv(f)
            body += f"<h2>{e(title)}</h2><p class=\"sub\">{e(sub)}</p>" + table_html(
                df, [c for c in df.columns if df[c].dtype != object])
    body += ('<h2>Caveats</h2><div class="note">Ablation choices were made on the same 9 labelled datasets that are '
             'scored here (leave-one-dataset-out inside each run), so small gains may not carry over; the organisers\' '
             'private labels for <span class="mono">unseen</span> are the independent test. v1/v2 numbers are a snapshot '
             f'from {e(res["baseline_created"])}.</div>')
    return page("Detect v1 v2 v3", body)


def dataset_page(ds: str, res: dict, preds: dict) -> str:
    runs, cat = res["runs"], res["_catalog"]
    lab = ds in res["labelled"]
    pb = preds["v3"]["blind"][preds["v3"]["blind"].dataset == ds].copy()
    pn = preds["v3"]["names"][preds["v3"]["names"].dataset == ds][
        ["table", "column", "privacy_role", "name_info", "tier2_used"]].rename(
        columns={"privacy_role": "names_role", "name_info": "names_info", "tier2_used": "names_tier2"})
    v2 = preds["v2"]["blind"][preds["v2"]["blind"].dataset == ds][["table", "column", "privacy_role"]].rename(
        columns={"privacy_role": "v2_role"})
    df = pb.merge(pn, on=["table", "column"], how="left").merge(v2, on=["table", "column"], how="left")
    if lab:
        df = df.merge(cat[cat.dataset == ds][["table", "column", "privacy_role", "subtype"]].rename(
            columns={"privacy_role": "gold", "subtype": "gold_sub"}), on=["table", "column"], how="left")
    body = (f'<nav class="top"><a href="index.html">← v1/v2/v3 overview</a><a href="../reports/{ds}_v1.html">{e(ds)} v1</a>'
            f'<a href="../reports/{ds}_v2.html">{e(ds)} v2</a></nav><h1>{e(ds)} · {e(LABEL["v3"])}</h1>'
            f'<p class="sub">{e(DESC_V3)}</p>')
    if lab:
        sb, sn = _sc(runs, "v3", "blind", ds), _sc(runs, "v3", "names", ds)
        s2b, s2n = _sc(runs, "v2", "blind", ds), _sc(runs, "v2", "names", ds)
        s1n = _sc(runs, "v1", "names", ds)
        body += kpis([
            ("macro-F1 · names hidden", fmt(sb["macro_f1"]), f'v2 {fmt(s2b["macro_f1"])}'),
            ("macro-F1 · with names", fmt(sn["macro_f1"]), f'v1 {fmt(s1n["macro_f1"])} · v2 {fmt(s2n["macro_f1"])}'),
            ("sensitive recall · hidden", fmt(sb["sensitive_recall"]), f'v2 {fmt(s2b["sensitive_recall"])}'),
            ("subtype acc. · hidden", fmt(sb.get("subtype_accuracy")), f'v2 {fmt(s2b.get("subtype_accuracy"))}'),
        ])
        body += f'<div class="card">{role_bars(sb, sn)}</div><h3>Confusion matrix (names hidden)</h3>' \
                f'<div class="card">{confusion(sb)}</div>'
    else:
        body += '<div class="note">No public labels for this dataset (scored privately by the organisers).</div>'
    body += ('<h2>Every column</h2><p class="sub">Main prediction = names hidden. name_info and tier 2 are from the '
             'run with names (with names hidden every column name is a code, so tier 2 is always LogReg). '
             'Red = wrong against the catalog; values in reasons are masked.</p>')
    for table, g in df.groupby("table", sort=False):
        nw = int((g.privacy_role != g.gold).sum()) if lab else 0
        dom = next((x for x in g.table_domain.dropna().astype(str) if x), "")
        rows = ""
        for _, r in g.iterrows():
            wrong = lab and r.privacy_role != r.gold
            changed = r.privacy_role != r.v2_role
            flags = (' <span class="src" style="color:var(--warn)">needs review</span>' if str(r.needs_review) == "True" else "") + \
                    (' <span class="src" style="color:var(--r-sensitive)">Art. 9</span>' if str(r.art9) == "True" else "")
            gold = (f'<td>{badge(r.gold)}<div class="src">{e(r.gold_sub)}</div></td>'
                    f'<td>{"<span class=ko>✗</span>" if wrong else "<span class=ok>✓</span>"}</td>') if lab else ""
            conf = float(r.confidence or 0)
            rows += (f'<tr class="{"wrong" if wrong else ""}"><td class="mono">{e(r.column)}</td>'
                     f'<td>{badge(r.privacy_role)}{flags}<div class="src">{e(r.subtype)}</div></td>'
                     f'<td>{badge(r.v2_role) if isinstance(r.v2_role, str) else ""}'
                     f'{" <span class=src>changed</span>" if changed else ""}</td>'
                     f'<td>{badge(r.names_role) if isinstance(r.names_role, str) else ""}</td>{gold}'
                     f'<td class="src">{fmt(float(r.names_info), 2) if pd.notna(r.names_info) else "–"}<br>{e(r.names_tier2)}</td>'
                     f'<td class="src"><span class="conf"><i style="width:{100 * min(conf, 1):.0f}%"></i></span>{conf:.2f}'
                     f'<br>{e(r.source)}</td><td class="reason">{e(sanitize(r.reason))}</td></tr>')
        summ = f'{e(table)}<span class="meta">{len(g)} columns'
        summ += f' · <span class="{"ko" if nw else "ok"}">{nw} wrong</span>' if lab else ""
        summ += (f' · domain: {e(sanitize(dom))}' if dom else "") + (" · Art. 9 table" if str(g.art9_table.iloc[0]) == "True" else "")
        summ += "</span>"
        body += (f'<details open><summary>{summ}</summary><div class="scroll"><table><tr><th>column</th>'
                 '<th>v3 (names hidden)</th><th>v2 (names hidden)</th><th>v3 with names</th>'
                 + ("<th>catalog</th><th></th>" if lab else "") +
                 f'<th>name_info<br>tier 2</th><th>confidence<br>decided by</th><th>reason</th></tr>{rows}</table></div></details>')
    return page(f"{ds} v3", body)


def build(root=None) -> list[Path]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    res = json.loads((OUT / "summary.json").read_text())
    _, _, cat_path = root_paths(root)
    res["_catalog"] = pd.read_csv(cat_path, dtype=str)
    preds = {"v3": {m: pd.read_csv(OUT / f"pred_v3_{m}.csv", dtype=str) for m in ("names", "blind")},
             "v2": {m: pd.read_csv(Path("out/compare") / f"pred_v2_{m}.csv", dtype=str) for m in ("names", "blind")}}
    files = []
    for ds in res["datasets"]:
        f = REPORTS / f"{ds}_v3.html"
        f.write_text(dataset_page(ds, res, preds))
        files.append(f)
    f = REPORTS / "index.html"
    f.write_text(index_page(res, preds))
    files.append(f)
    return files
