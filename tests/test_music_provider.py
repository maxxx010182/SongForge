from backend.services.sunoapi_org_client import SunoApiOrgClient


def test_sunoapi_map_success():
    assert SunoApiOrgClient._map_state("success") == "success"


def test_sunoapi_map_pending():
    assert SunoApiOrgClient._map_state("first_success") == "generating"
    assert SunoApiOrgClient._map_state("pending") == "generating"


def test_sunoapi_map_sensitive():
    assert SunoApiOrgClient._map_state("sensitive_word_error") == "failed"


def test_sunoapi_normalize_model():
    assert SunoApiOrgClient._normalize_model("V5_5") == "V5_5"
    assert SunoApiOrgClient._normalize_model("v5.5") == "V5_5"