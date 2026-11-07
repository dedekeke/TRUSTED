"""Table views of each pipeline step for the UI (server.api /api/jobs/{id}/steps/{step}).

Every view reads the files a stage already wrote and returns
  {"stats": [{"label", "value", "hint"?}], "tables": [{"id", "title", "note"?, "columns": [{"key", "title"}], "rows"}],
   "issues": [{"level": "error|warning|info", "code", "message"}]}
Views only re-shape: they never compute a privacy or utility number themselves (those come from the stage outputs
and pets-eval). They return labels, counts, statuses and digests only: never cell values, span text or row maps.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd

LABEL_FIELDS = ["table", "column", "privacy_role", "subtype", "confidence", "needs_review", "art9", "data_kind"]
# Detect v3 quality from its leave-one-dataset-out evaluation (server/detect README; offline, not this run)
DETECT_V3_EVAL = {"macro_f1_names": 0.854, "macro_f1_blind": 0.774, "span_f2": 0.998}
ISSUE_CODE = re.compile(r"^([a-z_]+):\s")
REVIEW_RX = re.compile(r"review_required: (\S+) is required by (.+?) but its label (\S+) is uncertain "
                       r"\(confidence ([0-9.]+)")


def _json(path: Path):
    return json.loads(path.read_text()) if path.is_file() else None


def _bool(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def _r(x, n=4):
    return None if x is None else round(float(x), n)


def table(id_: str, title: str, columns: list[tuple[str, str]], rows: list[dict], note: str | None = None) -> dict:
    t = {"id": id_, "title": title, "columns": [{"key": k, "title": v} for k, v in columns], "rows": rows}
    if note:
        t["note"] = note
    return t


def issues_from(messages: list, level: str) -> list[dict]:
    out = []
    for m in messages or []:
        m = str(m)
        code = ISSUE_CODE.match(m)
        out.append({"level": level, "code": code.group(1) if code else level, "message": m})
    return out


# ---------------------------------------------------------------- per-step views

def view_input(job: Path, ctx: dict) -> dict:
    info = _json(job / "input.json") or {"tables": []}
    rows = info["tables"]
    return {"stats": [{"label": "Bảng", "value": len(rows)},
                      {"label": "Dòng", "value": sum(r["rows"] for r in rows)},
                      {"label": "Cột", "value": sum(r["columns"] for r in rows)},
                      {"label": "Dung lượng (MB)", "value": round(sum(r["size_mb"] for r in rows), 1)}],
            "tables": [table("files", "File đầu vào", [("file", "File"), ("rows", "Dòng"), ("columns", "Cột"),
                                                       ("size_mb", "MB"), ("sha256", "sha256 (12)")], rows)],
            "issues": info.get("issues", [])}


def labels_rows(det: Path) -> list[dict]:
    if not (det / "labels.csv").is_file():
        return []
    lab = pd.read_csv(det / "labels.csv", dtype=str, keep_default_na=False)
    out = []
    for r in lab.to_dict("records"):
        out.append({k: (_r(r[k], 3) if k == "confidence" else _bool(r[k]) if k in ("needs_review", "art9")
                        else r[k]) for k in LABEL_FIELDS if k in r})
    return out


def view_detect(job: Path, ctx: dict) -> dict:
    det = ctx["pipeline"] / "detect"
    labels = labels_rows(det)
    roles = Counter(x["privacy_role"] for x in labels)
    spans = Counter()
    if (det / "spans.jsonl").is_file():
        with (det / "spans.jsonl").open() as fh:
            for line in fh:
                if line.strip():
                    spans[json.loads(line).get("entity_type", "?")] += 1
    link = (_json(det / "linkage.json") or {}).get("relations", [])
    bench = ctx.get("benchmark", {}).get("B1_detection_public") or {}
    quality = [{"detector": "B1 baseline (organisers, rules)", "macro_f1_names": _r(bench.get("macro_f1"), 3),
                "macro_f1_blind": None, "sensitive_recall": _r(bench.get("sensitive_recall"), 3)},
               {"detector": "Detect v3 (ours)", "macro_f1_names": DETECT_V3_EVAL["macro_f1_names"],
                "macro_f1_blind": DETECT_V3_EVAL["macro_f1_blind"], "sensitive_recall": None}]
    return {
        "stats": [{"label": "Cột đã gán nhãn", "value": len(labels)},
                  *({"label": r, "value": n} for r, n in roles.most_common()),
                  {"label": "Cần duyệt", "value": sum(x["needs_review"] for x in labels)},
                  {"label": "Span PII trong text", "value": sum(spans.values())}],
        "tables": [
            table("labels", "Nhãn từng cột", [("table", "Bảng"), ("column", "Cột"), ("privacy_role", "Role"),
                                              ("subtype", "Subtype"), ("confidence", "Độ tin cậy"),
                                              ("art9", "Art. 9"), ("needs_review", "Cần duyệt")], labels),
            table("spans", "PII trong free text (số span theo loại)", [("label", "Loại"), ("count", "Số span")],
                  [{"label": k, "count": v} for k, v in spans.most_common()]),
            table("linkage", "Liên kết phát hiện được", [("kind", "Loại"), ("left", "Từ"), ("right", "Tới"),
                                                         ("confidence", "Độ tin cậy"), ("needs_review", "Cần duyệt")],
                  [{"kind": r.get("kind"), "left": _ref(r.get("left")), "right": _ref(r.get("right")),
                    "confidence": _r(r.get("confidence"), 3), "needs_review": r.get("needs_review")} for r in link]),
            table("quality", "Chất lượng detector so với baseline", [
                ("detector", "Detector"), ("macro_f1_names", "Macro-F1 (có tên cột)"),
                ("macro_f1_blind", "Macro-F1 (che tên cột)"), ("sensitive_recall", "Sensitive recall")], quality,
                note="Số đánh giá offline leave-one-dataset-out trên 9 dataset có nhãn (README server/detect), "
                     "không đo trên lần chạy này."),
        ],
        "issues": []}


def _ref(x) -> str:
    return f"{x.get('table')}.{x.get('column')}" if isinstance(x, dict) else str(x or "")


def review_items(ctx: dict) -> list[dict]:
    """needs_review labels, which task needs them (from the select errors) and any confirmation."""
    labels = labels_rows(ctx["pipeline"] / "detect")
    required = {}
    for sel in ctx.get("select_dirs", []):
        for e in (_json(sel / "decisions.json") or {}).get("errors", []):
            m = REVIEW_RX.match(str(e))
            if m:
                required[m.group(1)] = m.group(2)
    confirmed = {}
    if ctx.get("confirm") and Path(ctx["confirm"]).is_file():
        for r in pd.read_csv(ctx["confirm"], dtype=str, keep_default_na=False).to_dict("records"):
            confirmed[f"{r['table']}.{r['column']}"] = f"{r['privacy_role']}/{r['subtype']}"
    rows = []
    for x in labels:
        ref = f"{x['table']}.{x['column']}"
        if x["needs_review"] or ref in required or ref in confirmed:
            rows.append({"table": x["table"], "column": x["column"], "privacy_role": x["privacy_role"],
                         "subtype": x["subtype"], "confidence": x["confidence"],
                         "required_by": required.get(ref, ""), "blocking": ref in required,
                         "confirmed": confirmed.get(ref, "")})
    rows.sort(key=lambda r: (not r["blocking"], r["confidence"] or 0))
    return rows


def view_review(job: Path, ctx: dict) -> dict:
    rows = review_items(ctx)
    return {"stats": [{"label": "Cột được cờ cần duyệt", "value": len(rows)},
                      {"label": "Đang chặn Select", "value": sum(r["blocking"] for r in rows)},
                      {"label": "Đã xác nhận", "value": sum(bool(r["confirmed"]) for r in rows)}],
            "tables": [table("review", "Cột cần người duyệt", [
                ("table", "Bảng"), ("column", "Cột"), ("privacy_role", "Role (detect)"), ("subtype", "Subtype"),
                ("confidence", "Độ tin cậy"), ("required_by", "Task cần cột này"), ("blocking", "Đang chặn"),
                ("confirmed", "Đã xác nhận")], rows,
                note="Chỉ cột 'đang chặn' bắt buộc phải xác nhận; xác nhận được ghi vào provenance (confirm_sha256).")],
            "issues": []}


def view_select(job: Path, ctx: dict) -> dict:
    plan = _json(ctx["select"] / "decisions.json") if ctx.get("select") else None
    if plan is None:
        return {"stats": [], "tables": [], "issues": ctx.get("log_issues", [])}
    cols = plan.get("columns", [])
    actions = Counter(c.get("action") for c in cols)
    rows = [{"table": c["table"], "column": c["column"], "privacy_role": c.get("privacy_role"),
             "subtype": c.get("subtype"), "action": c.get("action"), "method": c.get("method") or "",
             "params": json.dumps(c.get("params") or {}, ensure_ascii=False) if c.get("params") else "",
             "required_by": ", ".join(c.get("required_by") or []), "confidence": _r(c.get("confidence"), 3),
             "reason": c.get("reason", "")} for c in cols]
    tabs = [{"table": t, "action": d.get("action"), "record_key": d.get("record_key") or "",
             "reason": d.get("reason", "")} for t, d in (plan.get("tables") or {}).items()]
    return {"stats": [{"label": "Trạng thái", "value": plan.get("status")},
                      {"label": "Kịch bản", "value": plan.get("scenario") or plan.get("source")},
                      {"label": "Trust level", "value": plan.get("trust_level")},
                      *({"label": a, "value": n} for a, n in actions.most_common())],
            "tables": [table("columns", "PET được chọn cho từng cột", [
                ("table", "Bảng"), ("column", "Cột"), ("privacy_role", "Role"), ("subtype", "Subtype"),
                ("action", "Hành động"), ("method", "Phương pháp"), ("params", "Tham số"),
                ("required_by", "Task cần"), ("confidence", "Độ tin cậy"), ("reason", "Lý do")], rows),
                table("tables", "Bảng được phát hành", [("table", "Bảng"), ("action", "Quyết định"),
                                                       ("record_key", "Record key"), ("reason", "Lý do")], tabs)],
            "issues": issues_from(plan.get("errors"), "error") + issues_from(plan.get("warnings"), "warning")}


def view_search(job: Path, ctx: dict) -> dict:
    res = _json(ctx["search"] / "decisions.json") if ctx.get("search") else None
    if res is None:
        return {"stats": [], "tables": [], "issues": ctx.get("log_issues", [])}
    out = res.get("outcome") or {}
    m = res.get("measured") or {}
    targets = out.get("targets") or {}
    risk = []
    for t, a in (out.get("achieved") or {}).items():
        if t == "utility" or not isinstance(a, dict):
            continue
        risk.append({"table": t, "target_k": targets.get("k"), "min_k": a.get("min_k"),
                     "share_below_k": _r(a.get("share_below_k")), "unknown_subject_rows": a.get("unknown_subject_rows"),
                     "l": json.dumps(a.get("l")) if a.get("l") else "", "t": json.dumps(a.get("t")) if a.get("t") else ""})
    tau = m.get("tau", targets.get("tau"))
    util = []
    for task, score in (m.get("utility") or {}).items():
        base = (m.get("baseline_utility") or {}).get(task)
        floor = None if base is None or tau is None else base * tau
        util.append({"task": task, "score": _r(score), "unsearched": _r(base), "floor": _r(floor),
                     "ok": None if floor is None or score is None else score >= floor - 1e-12,
                     "b2": _r(ctx.get("baseline_tasks", {}).get("B2", {}).get(task), 3),
                     "b2k": _r(ctx.get("baseline_tasks", {}).get("B2K", {}).get(task), 3)})
    viol = [{"metric": v.get("metric"), "table": v.get("table"), "target": json.dumps(v.get("target")),
             "achieved": json.dumps(v.get("achieved")), "requirements": ", ".join(v.get("requirements") or [])}
            for v in out.get("violations", [])]
    trace = [{"evaluation": e.get("evaluation"), "phase": e.get("phase"), "changed_column": e.get("changed_column", ""),
              "accepted": e.get("accepted"), "reason": e.get("reason", ""),
              "information_loss": _r(e.get("information_loss")), "suppressed_fraction": _r(e.get("suppressed_fraction")),
              "max_share_below_k": _r(max((r.get("share_below_k") or 0 for r in (e.get("risk") or {}).values()),
                                          default=None))}
             for e in res.get("search_trace", [])]
    budget = out.get("budget") or {}
    return {"stats": [{"label": "Trạng thái", "value": res.get("status")},
                      {"label": "Được duyệt phát hành", "value": out.get("approved")},
                      {"label": "Lượt đánh giá", "value": f"{budget.get('used')}/{budget.get('limit')}"},
                      {"label": "Information loss", "value": _r(m.get("information_loss"), 3)},
                      {"label": "Mục tiêu", "value": ", ".join(f"{k}={v}" for k, v in targets.items()
                                                                if k in ("k", "l", "t", "max_suppression"))}],
            "tables": [table("risk", "Rủi ro: mục tiêu vs đạt được (theo bảng)", [
                ("table", "Bảng"), ("target_k", "k mục tiêu"), ("min_k", "k nhỏ nhất"),
                ("share_below_k", "% bản ghi dưới k"), ("unknown_subject_rows", "Dòng không rõ chủ thể"),
                ("l", "l-diversity"), ("t", "t-closeness")], risk),
                table("utility", "Utility theo task (đo trên dữ liệu đã bảo vệ)", [
                    ("task", "Task"), ("score", "Ours"), ("unsearched", "Trước search"), ("floor", "Ngưỡng τ"),
                    ("ok", "Đạt"), ("b2", "B2"), ("b2k", "B2-k")], util,
                    note="B2/B2-k: điểm task trong results/benchmark.json của ban tổ chức."),
                table("violations", "Vi phạm còn lại", [("metric", "Chỉ số"), ("table", "Bảng"),
                                                        ("target", "Mục tiêu"), ("achieved", "Đạt"),
                                                        ("requirements", "Task liên quan")], viol),
                table("trace", "Các bước search", [
                    ("evaluation", "#"), ("phase", "Pha"), ("changed_column", "Cột thay đổi"), ("accepted", "Nhận"),
                    ("reason", "Lý do"), ("information_loss", "Info loss"), ("suppressed_fraction", "% xoá"),
                    ("max_share_below_k", "Max % dưới k")], trace)],
            "issues": issues_from(res.get("errors"), "error") + issues_from(res.get("warnings"), "warning")
            + ([{"level": "error", "code": "conflict", "message": res["conflict"].get("reason", "")}]
               if res.get("conflict") else [])}


def view_transform(job: Path, ctx: dict) -> dict:
    tra = ctx.get("transform")
    man = _json(tra / "manifest.json") if tra else None
    diag = _json(tra / "diagnostics.json") if tra else None
    if man is None:
        iss = ctx.get("log_issues", [])
        if diag:
            iss = iss + [{"level": "error", "code": "refused", "message": json.dumps(diag, default=str)[:2000]}]
        return {"stats": [], "tables": [], "issues": iss}
    stats = _json(tra / "transform_stats.json") or {}
    ic = _json(tra / "reports" / "identifier_check.json") or {}
    checks = [{"name": c.get("name"), "status": c.get("status"), "problems": c.get("problems")}
              for c in man.get("checks", [])]
    exported = [{"table": t, "rows": (stats.get("rows") or {}).get(t), "columns": (stats.get("columns") or {}).get(t),
                 "suppressed_rows": (stats.get("suppressed_rows") or {}).get(t, 0),
                 "suppressed_cells": json.dumps((stats.get("suppressed_cells") or {}).get(t, {})) or ""}
                for t in (man.get("tables") or {})]
    raw, fp, un = ic.get("raw_totals") or {}, ic.get("classified_false_positives") or {}, ic.get("unexplained") or {}
    ident = [{"label": k, "raw_hits": raw.get(k, 0), "false_positives": (fp.get(k) or {}).get("count", 0),
              "residual": un.get(k, 0), "reason": (fp.get(k) or {}).get("reason", "")}
             for k in sorted(set(raw) | set(un))]
    red = [{"column": c, "method": m} for c, m in (stats.get("redaction") or {}).items()]
    return {"stats": [{"label": "Validation", "value": man.get("validation_status")},
                      {"label": "Phát hành được duyệt", "value": man.get("approved_release")},
                      {"label": "Bảng xuất", "value": len(man.get("tables") or {})},
                      {"label": "Bảng giữ lại (không xuất)", "value": len(man.get("withheld_tables") or [])},
                      {"label": "Checks đạt", "value": f"{sum(c['status'] == 'passed' for c in checks)}/{len(checks)}"}],
            "tables": [table("checks", "Kiểm tra sau khi ghi file", [("name", "Check"), ("status", "Kết quả"),
                                                                     ("problems", "Lỗi")], checks),
                       table("exported", "Bảng đã xuất (protected/)", [
                           ("table", "Bảng"), ("rows", "Dòng"), ("columns", "Cột"),
                           ("suppressed_rows", "Dòng bị xoá"), ("suppressed_cells", "Ô bị xoá")], exported),
                       table("redaction", "Redaction free text", [("column", "Cột"), ("method", "Cách redact")], red),
                       table("identifiers", "Quét định danh còn sót (pets-eval check)", [
                           ("label", "Loại"), ("raw_hits", "Khớp pattern"), ("false_positives", "Dương tính giả"),
                           ("residual", "Còn sót thật"), ("reason", "Giải thích")], ident)],
            "issues": [{"level": "warning", "code": "not_approved", "message": "Export không được duyệt (--allow-unapproved)"}]
            if man.get("approved_release") is False else []}


def summarise_scorecard(rep: dict) -> dict:
    """Same definition as the organisers' baselines/run_all.py summarise(), so rows are comparable."""
    s = rep["summary"]
    risks = rep.get("risk_components", {})
    reid = [v for k, v in risks.items() if "reid" in k.lower() or "linkage" in k.lower()]
    resid = [v for k, v in risks.items() if "residual" in k.lower() or "direct" in k.lower()]
    return {"privacy": s["privacy"], "utility": s["utility"], "composite": s["composite"],
            "worst_reid": max(reid) if reid else None, "residual_identifiers": max(resid) if resid else None,
            "utility_tasks": {u["id"]: (None if u["score"] is None else round(u["score"], 3)) for u in rep["utility"]}}


def view_evaluate(job: Path, ctx: dict) -> dict:
    tra = ctx.get("transform")
    rep = _json(tra / "reports" / "scorecard.json") if tra else None
    if rep is None:
        return {"stats": [], "tables": [], "issues": [{"level": "info", "code": "no_scorecard",
                                                       "message": "Chưa có scorecard (Transform chưa chạy xong)."}]}
    ours = summarise_scorecard(rep)
    ds, sc = ctx.get("dataset"), ctx.get("scenario")
    bench = ctx.get("benchmark", {})
    # our scorecard runs with the scenario, so its utility covers the scenario's tasks only: it is compared in the
    # scenario column, never against the baselines' all-task utility
    rows = [{"method": "Ours (pipeline này)", **{k: _r(ours[k]) for k in ("privacy", "composite",
                                                                          "worst_reid", "residual_identifiers")},
             "utility": None, "scenario_utility": _r(ours["utility"])}]
    for name, key in (("B0: chỉ xoá định danh trực tiếp", "B0"), ("B2: SDC cổ điển", "B2"),
                      ("B2-k: B2 + suppression k≥5", "B2K")):
        b = bench.get(f"{key}_{ds}")
        if b:
            rows.append({"method": name, **{k: _r(b.get(k)) for k in ("privacy", "utility", "composite",
                                                                       "worst_reid", "residual_identifiers")},
                         "scenario_utility": _r((b.get("utility_by_scenario") or {}).get(sc))})
    tasks = []
    for u in rep.get("utility", []):
        row = {"task": u["id"], "description": u.get("description", ""), "required": u.get("required"),
               "ours": _r(u.get("score"), 3)}
        for key in ("B0", "B2", "B2K"):
            row[key.lower()] = _r(((bench.get(f"{key}_{ds}") or {}).get("utility_tasks") or {}).get(u["id"]), 3)
        tasks.append(row)
    risk = [{"component": k, "risk": _r(v)} for k, v in (rep.get("risk_components") or {}).items()]
    has_b = len(rows) > 1
    return {"stats": [{"label": "Privacy", "value": _r(ours["privacy"], 3)},
                      {"label": "Utility", "value": _r(ours["utility"], 3)},
                      {"label": "Composite", "value": _r(ours["composite"], 3)},
                      {"label": "Worst re-id", "value": _r(ours["worst_reid"], 3)}],
            "tables": [table("compare", "So sánh với baseline của ban tổ chức", [
                ("method", "Phương pháp"), ("privacy", "Privacy"), ("utility", "Utility (tất cả task)"),
                ("composite", "Composite"), ("worst_reid", "Worst re-id"),
                ("residual_identifiers", "Định danh sót"), ("scenario_utility", f"Utility {sc or ''}")], rows,
                note="Baseline từ results/benchmark.json (scorecard chạy không theo kịch bản); cột utility theo kịch "
                     "bản dùng utility_by_scenario. Ours: reports/scorecard.json của Transform, tóm tắt bằng đúng "
                     "công thức summarise() của baselines/run_all.py." if has_b else
                "Không có baseline cho dataset này (chỉ có cho 9 dataset của package)."),
                table("tasks", "Utility từng task", [("task", "Task"), ("description", "Mô tả"),
                                                      ("required", "Kịch bản cần"), ("ours", "Ours"), ("b0", "B0"),
                                                      ("b2", "B2"), ("b2k", "B2-k")], tasks),
                table("risks", "Thành phần rủi ro (scorecard)", [("component", "Thành phần"), ("risk", "Rủi ro")], risk)],
            "issues": [{"level": "info", "code": "self_assessment",
                        "message": rep["summary"].get("label", "self-assessment, not the official judging score")}]}


VIEWS = {"input": view_input, "detect": view_detect, "review": view_review, "select": view_select,
         "search": view_search, "transform": view_transform, "evaluate": view_evaluate}


def summary(step: str, job: Path, ctx: dict) -> str:
    """One line for the accordion header."""
    try:
        v = VIEWS[step](job, ctx)
    except Exception:  # noqa: BLE001 - a summary must never break the status endpoint
        return ""
    st = {s["label"]: s["value"] for s in v["stats"]}
    if step == "input":
        return f"{st.get('Bảng', 0)} bảng · {st.get('Dòng', 0):,} dòng · {st.get('Cột', 0)} cột"
    if step == "detect":
        return f"{st.get('Cột đã gán nhãn', 0)} cột · {st.get('Cần duyệt', 0)} cần duyệt · " \
               f"{st.get('Span PII trong text', 0):,} span PII"
    if step == "review":
        return f"{st.get('Đang chặn Select', 0)} cột đang chặn · {st.get('Đã xác nhận', 0)} đã xác nhận"
    if step == "select":
        acts = " · ".join(f"{s['value']} {s['label']}" for s in v["stats"][3:])
        return f"{st.get('Trạng thái', '')} · {acts}"
    if step == "search":
        return f"{st.get('Trạng thái', '')} · {st.get('Lượt đánh giá', '')} lượt"
    if step == "transform":
        return f"{st.get('Validation', '')} · {st.get('Bảng xuất', 0)} bảng xuất · checks {st.get('Checks đạt', '')}"
    if step == "evaluate":
        return f"privacy {st.get('Privacy')} · utility {st.get('Utility')} · composite {st.get('Composite')}"
    return ""
