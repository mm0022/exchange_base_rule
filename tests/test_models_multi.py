from exchange_monitor.models import ExchangeResult, RunResult


def test_exchange_result_defaults():
    ex = ExchangeResult(name="OKX", is_baseline=True)
    assert ex.name == "OKX"
    assert ex.doc_changes == [] and ex.anns_new == [] and ex.anns_del == []
    assert ex.fee_supported is False and ex.fee_changed is False


def test_run_result_holds_exchanges():
    r = RunResult(generated_at="2026-07-01 00:00 UTC",
                  exchanges=[ExchangeResult(name="OKX", is_baseline=False)])
    assert r.generated_at.endswith("UTC")
    assert r.exchanges[0].name == "OKX"
