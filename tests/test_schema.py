from lambda_rca.agent.schema import INVALID_ANSWER, parse_answer


def test_valid_answer_with_fence():
    text = 'Here it is:\n```json\n{"anomaly": true, "root_cause_layer": "IAM", "function": "f",' \
           ' "candidates": ["a", "b"], "explanation": "x"}\n```'
    ans, valid, err = parse_answer(text)
    assert valid and err is None
    assert ans["candidates"] == ["a", "b"]


def test_normal_window_answer():
    text = '{ "anomaly": false, "root_cause_layer": "NONE", "function": null, "candidates": [], ' \
           '"explanation": "No errors {really}." }'
    ans, valid, _ = parse_answer(text)
    assert valid and ans["anomaly"] is False


def test_schema_violation_counts_as_anomaly_without_candidate():
    # anomaly false but a layer given -> violates the if/then rule of Appendix C
    text = '{"anomaly": false, "root_cause_layer": "IAM", "function": null, "candidates": [], "explanation": ""}'
    ans, valid, err = parse_answer(text)
    assert not valid and err
    assert ans == INVALID_ANSWER and ans["anomaly"] is True and ans["candidates"] == []


def test_too_many_candidates_and_garbage():
    text = '{"anomaly": true, "root_cause_layer": "IAM", "function": "f", "candidates": ["1","2","3","4"],' \
           ' "explanation": ""}'
    assert parse_answer(text)[1] is False
    assert parse_answer("I could not decide.")[1] is False
    assert parse_answer("")[1] is False
