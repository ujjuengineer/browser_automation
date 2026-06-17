"""
playwright is the global pytest fixture which is provided by the pytest

The playwright fixture manages the entire lifecycle of the Playwright core driver.
-> Before the test starts: It launches the Playwright driver process behind the scenes.
-> During the test: It gives you access to the API (allowing you to call .chromium.launch(), etc.).
-> After the test finishes: It automatically cleans up, closes the driver, and frees up your system's memory—even if your test fails halfway through.
"""


"""
In web automation, "headless" refers to running a web browser without a graphical user interface (GUI).

When a browser runs headlessly, it is fully functioning—it loads pages, clicks buttons, downloads files, and executes JavaScript just like normal—but it does all of this completely in the background. You won't see a browser window pop up on your screen.

To the website: Playwright looks exactly like a real human user opening Chrome.
"""


def test_playwrightBasic(playwright):
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://rahulshettyacademy.com")

"""
NOTE : code explanation 

browser = playwright.chromium.launch(headless=False)
-> Launches an instance of the Chromium browser (the open-source engine behind Google Chrome and Microsoft Edge).
-> The details: By default, automated tests run in "headless" mode (in the background without a visual window). Setting headless=False forces Playwright to physically open the browser window on your screen so you can watch the test execute.

context = browser.new_context()
-> Creates a new, completely isolated browser context.
-> The details: Think of a browser context like an Incognito or Private browsing window. It does not share cookies, cache, or local storage with other contexts. This is incredibly useful in testing because it ensures a completely clean slate, preventing data from a previous test from messing up the current one.

page = context.new_page()
-> Opens a new tab or page within that isolated browser context.
-> The details: This page object is what you will use to actually interact with the website (clicking buttons, typing text, scrolling, etc.).

page.goto("https://rahulshettyacademy.com")
-> Commands the open page to navigate to the specified URL.
NOTE: The details: Playwright will automatically wait for the page to fire its load event before moving on to any subsequent lines of code, making it less prone to the timing issues common in older tools like Selenium.
"""


"""
[playwright fixture]  <-- The argument in your function (The core driver)
         │
         └── [Browser] (Chromium, Firefox, or WebKit)
                 │
                 └── [Browser Context] (Isolated incognito session)
                         │
                         └── [Page] (The actual tab navigating to a URL)
"""


# shortcut for above test
from playwright.sync_api import Page

def test_playwrightShortcut(page:Page):
    page.goto("https://rahulshettyacademy.com")

"""
def test_playwrightShortcut(page: Page):

What it does: Defines the test function and requests the page fixture.
The details: Notice that instead of passing playwright as an argument like the first script, this one passes page. This is a built-in pytest-playwright shortcut fixture.

When pytest sees page, it automatically executes all those hidden steps for you. It goes into the background and secretly runs:
    playwright.chromium.launch()
    browser.new_context()
    context.new_page()


page.goto("https://rahulshettyacademy.com")
Commands the automatically created browser tab to navigate to the website.


NOTE : A Quick Note on Headless Mode
Because Playwright is handling the browser creation entirely behind the scenes here, you can no longer pass headless=False inside the code.

If you want to actually see the browser open when using this shortcut, you control it from your terminal command line instead when running the test:

pytest --headed
"""