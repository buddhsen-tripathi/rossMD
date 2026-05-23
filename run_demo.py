import asyncio, time, json
from ross.orchestrator import Orchestrator

SCENARIO = ("UnitedHealthcare denied our client hospital's claim for a 4-day inpatient cardiac "
            "admission as 'not medically necessary,' downgrading it to observation and citing MCG "
            "care guidelines. The patient presented with chest pain, elevated troponins, and a "
            "positive stress test, and was admitted by the attending cardiologist. The plan is an "
            "ERISA self-funded plan; we are at the internal appeal stage with the deadline in 12 "
            "days. Build the appeal to overturn the denial.")

t0 = time.time()
async def emit(ev):
    el = time.time() - t0; p = ev.get("payload", {}); extra = ""
    if ev["event"] == "done" and "issues" in p:
        extra = " :: " + ", ".join(i["label"] for i in p["issues"])
    elif ev["event"] == "retrieved": extra = f" :: {len(p.get('authorities',[]))} authorities"
    elif ev["event"] == "verdict": extra = f" :: {p.get('verdict')} — \"{p.get('one_liner','')}\""
    elif ev["event"] == "done" and "posture" in p: extra = f" :: posture={p.get('posture')}"
    elif ev["event"] == "llm_call": extra = f" :: {p.get('model','').split('/')[-1]} {p.get('completion_tokens')}tok"
    print(f"[{el:6.1f}s] {ev['agent']:14} {ev['event']:13}{extra}", flush=True)

async def main():
    bb = await Orchestrator(emit).run(SCENARIO)
    print("\n===== HARVEY ====="); print(json.dumps(bb.get("harvey", {}), indent=2)[:900])
    d = bb.get("draft", {}); print("\n===== DRAFT (head) ====="); print(d.get("doc_type"),"—",d.get("title")); print((d.get("body_markdown") or "")[:1400])
    print(f"\n===== TOTAL {time.time()-t0:.1f}s | run_id={bb['run_id']} =====")
asyncio.run(main())
