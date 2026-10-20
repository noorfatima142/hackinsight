import json
import pandas as pd, gradio as gr
from config import *
from rag import InsightAgent

agent = InsightAgent()

def age_h(s):
    try: return (pd.Timestamp.now(tz="UTC") - pd.Timestamp(s)).total_seconds() / 3600
    except Exception: return None

def load_all():
    st = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    head = (f"**Last successful run:** {st.get('last_success_utc', 'never')} UTC  \n"
            f"**Latest run:** {st.get('last_run_status', 'unknown')} (run {st.get('run_id', '-')}, {st.get('seconds', '-')} s)  \n"
            f"{('**Error:** ' + st['error']) if st.get('error') else ''}")
    rows = []
    for name, s in (st.get("sources") or {}).items():
        a = age_h(s.get("last_fetch_utc"))
        rows.append({"source": name, "last_fetch_utc": s.get("last_fetch_utc"),
                     "fetch_age_h": None if a is None else round(a, 1),
                     "status": "LATE" if (a is None or a > 2) else "OK", "latest_data_utc": s.get("latest_data_utc")})
    qual = pd.DataFrame()
    if QUALITY_LOG.exists():
        q = pd.read_csv(QUALITY_LOG)
        q = q[q.run_id == st.get("run_id")] if (q.run_id == st.get("run_id")).any() else q[q.run_id == q.run_id.iloc[-1]]
        qual = q.groupby(["table", "rule", "action"], as_index=False)[["rows_affected", "rows_total"]].sum()
    metrics = "Model not trained yet."
    if (DATA / "metrics.json").exists():
        m = json.loads((DATA / "metrics.json").read_text())
        metrics = (f"**Baseline** ({m['baseline']}): MAE {m['baseline_mae']}  \n**Model** (LightGBM): MAE {m['model_mae']} "
                   f"({m['improvement_pct']}% better)  \n10-90% interval coverage on test: {m['interval_coverage']}")
    groups = pd.read_csv(DATA / "errors_by_group.csv") if (DATA / "errors_by_group.csv").exists() else pd.DataFrame()
    return head, pd.DataFrame(rows), qual, metrics, groups

def ask(q):
    r = agent.answer(q)
    return r["answer"], ", ".join(r["row_ids"][:50]) or "-", "; ".join(r["sources"]) or "-"

with gr.Blocks(title="Pakistan PM2.5 - HackInsight") as demo:
    gr.Markdown("# Pakistan PM2.5: data freshness, quality and forecasts")
    with gr.Tab("Pipeline status"):
        btn = gr.Button("Refresh")
        head, fresh = gr.Markdown(), gr.Dataframe(label="Data freshness")
        qual = gr.Dataframe(label="Data Quality Agent: decisions in the latest run")
        mm, grp = gr.Markdown(), gr.Dataframe(label="Errors by station and season (test set)")
        outs = [head, fresh, qual, mm, grp]
        btn.click(load_all, outputs=outs); demo.load(load_all, outputs=outs)
    with gr.Tab("Insight Agent"):
        q = gr.Textbox(label="Ask about air quality in a station's city")
        a, ids, srcs = gr.Textbox(label="Answer", lines=8), gr.Textbox(label="Gold row IDs used"), gr.Textbox(label="Sources")
        gr.Button("Ask").click(ask, q, [a, ids, srcs])

if __name__ == "__main__":
    demo.launch()