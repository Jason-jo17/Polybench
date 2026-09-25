from polybench.sandbox.policy import NETWORK, MEMORY

def test_policy_constants():
    assert NETWORK == "none"
    assert MEMORY == "256m"
