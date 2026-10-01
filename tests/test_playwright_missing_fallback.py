import pytest

import certhub.site_automation as site_automation


def test_run_site_reports_missing_playwright_without_crashing_import():
    with pytest.raises(site_automation.SiteAutomationError, match="Playwright|navegador"):
        site_automation.run_site(
            consultation_id="consulta-1",
            site_code="fgts",
            document="12.345.678/0001-95",
            on_status=lambda *args, **kwargs: None,
            on_captcha=lambda *args, **kwargs: None,
        )
