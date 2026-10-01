from certhub.core.models import EmissionResult


def test_emission_result_timestamp_is_utc_aware():
    result = EmissionResult(portal="fgts", document="12.345.678/0001-95", success=True)

    assert result.timestamp.endswith("Z")
    assert "T" in result.timestamp
