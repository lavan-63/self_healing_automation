import os

import pytest

from sample_app import build


@pytest.fixture(scope="session")
def site():
    build.main()
    return build.HERE / "site"


@pytest.fixture(scope="session")
def driver():
    from selenium import webdriver

    if os.getenv("BROWSER", "chrome").lower() == "edge":
        options = webdriver.EdgeOptions()
        factory = webdriver.Edge
    else:
        options = webdriver.ChromeOptions()
        factory = webdriver.Chrome
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,900")
    d = factory(options=options)
    yield d
    d.quit()
