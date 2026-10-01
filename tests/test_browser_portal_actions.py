from certhub.core.models import EmissionRequest
from certhub.portals.fgts import FGTSPortal


def test_portal_browser_actions_support_form_interaction():
    portal = FGTSPortal(EmissionRequest(portal="fgts", document="12.345.678/0001-95"))
    page = portal.open_browser()
    page.set_content(
        """
        <html>
            <body>
                <input id="documento" value="" />
                <button id="submit">Enviar</button>
            </body>
        </html>
        """
    )

    portal.fill_field("#documento", "12.345.678/0001-95")
    portal.click("#submit")

    assert page.locator("#documento").input_value() == "12.345.678/0001-95"
    portal.close_browser()
