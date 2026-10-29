import pytest
from load_quoting_swarm.chain.explanations import validate_explanation
from load_quoting_swarm.inference import InferenceError


@pytest.mark.parametrize("value", [{}, {"summary": ""}, {"summary": "safe", "risk_flags": "oops", "confidence": .8}, {"summary": "safe", "risk_flags": [], "confidence": True}, {"summary": "safe", "risk_flags": [], "confidence": 2}])
def test_empty_or_invalid_model_output_is_not_evidence(value):
    with pytest.raises(InferenceError):
        validate_explanation(value)


def test_nonempty_explanation_is_accepted():
    value = {"summary": "The driver needs manual dispatch because no legal home leg exists.", "risk_flags": ["NEEDS_HUMAN"], "confidence": .9}
    assert validate_explanation(value) == value
