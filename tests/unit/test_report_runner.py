import json

from rqg.evals.dataset import load_golden
from rqg.evals.judge import HeuristicJudge, average_precision, median_of
from rqg.evals.report import compute_kpis, render_markdown
from rqg.evals.runner import EvalRunner, library_versions, write_run


def test_median_of_repeats():
    vals = iter([0.2, 0.9, 0.8])
    med, samples = median_of(lambda: next(vals), 3)
    assert med == 0.8 and samples == [0.2, 0.9, 0.8]
    assert median_of(lambda: None, 3) == (None, [])


def test_average_precision():
    assert average_precision(["a", "b"], {"a"}) == 1.0
    assert average_precision(["b", "a"], {"a"}) == 0.5
    assert average_precision(["a"], set()) is None


def test_heuristic_judge():
    j = HeuristicJudge()
    ctx = ["AeroPure 500 filter life: about 8 months."]
    assert j.faithfulness("Filter life is about 8 months. [ap500_specs]", ctx) == 1.0
    assert j.faithfulness("It runs on solar power from Mars.", ctx) == 0.0
    assert j.faithfulness("", ctx) is None
    assert j.answer_relevancy("filter life AeroPure 500", "about 8 months filter life", []) >= 0.5
    assert j.answer_relevancy("the", "x", []) is None


def test_runner_on_subset(settings, assistant):
    ds = load_golden(settings.golden_path)
    pick = [ds.by_id()[i] for i in ("sf-002", "oos-001", "bt-001", "tc-001", "mt-001", "cf-001")]
    run = EvalRunner(settings, assistant).run(pick, ds.version, "custom")
    assert run["meta"]["mode"] == "mock" and run["meta"]["n_cases"] == 6
    ids = [c["case_id"] for c in run["cases"]]
    assert ids == sorted(ids)
    by = {c["case_id"]: c for c in run["cases"]}
    assert by["bt-001"]["observed_behavior"] == "refuse" and by["bt-001"]["passed"]
    assert by["tc-001"]["tools_called"][0]["name"] == "check_warranty"
    for c in run["cases"]:  # faithfulness is scored exactly when the assistant answered
        assert (c["scores"]["faithfulness"] is not None) == (c["observed_behavior"] == "answer")
    assert run["kpis"]["refusal_recall"] == 1.0
    jp, mp = write_run(run, settings.reports_dir)
    assert json.loads(jp.read_text())["meta"]["run_id"] == run["meta"]["run_id"]
    text = mp.read_text()
    assert "MOCK MODE" in text and "Headline KPIs" in text
    assert library_versions()["deepeval"] == "4.3.3"


def test_kpis_edge_cases():
    k = compute_kpis([])
    assert k["pass_rate"] is None and k["hallucination_rate"] is None
    run = {
        "meta": {
            "run_id": "x",
            "mode": "real",
            "subset": "full",
            "n_cases": 0,
            "dataset_version": "1.0.0",
            "git_sha": "a",
            "prompt_version": "v1",
            "app_model": "m",
            "judge": "j",
            "judge_repeats": 3,
            "embedding_backend": "onnx",
            "wall_time_s": 0,
            "judge_calls": 0,
        },
        "kpis": k,
        "per_category": {},
        "cases": [],
    }
    assert "MOCK" not in render_markdown(run)
