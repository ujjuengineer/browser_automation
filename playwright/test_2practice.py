from playwright.sync_api import Page, Playwright, expect
import time

def test_coreLocator(page:Page):
    page.goto("https://rahulshettyacademy.com/loginpagePractise")
    page.get_by_label("Username:").fill("rahulshettyacademy")
    page.get_by_label("Password:").fill("Learning@830$3mK2")
    page.get_by_role("combobox").select_option("teach")
    page.locator("#terms").check() # you can also use click()
    page.locator("#signInBtn").click()
    time.sleep(10)

"""
there is certain limitation in using get_by_label()

<label> Password <input type="password" /> </label>

if the input tag is inside the label, then only get by label will works, otherwise it will not!

it will also work in the case if : 
    inside label we have used the for=""
    and inside the input we have used the id="" which is equals to the for value

<label for="usename">username:</label>
<input id="username" />
"""


"""
NOTE : 
expect(page.get_by_text("Incorrect username/password.")).to_be_visible()
-> the expect function along with to_be_visible() is use to assert that a particular element is present and displayed on the webpage. 
"""

"""
read about assertion in the playwright
playwright gives you auto wait feature, which will automatically wait for certain event to happen, read it through documentation !!
"""


# running in the firefox browser
def test_firefoxBrowser(playwright:Playwright):
    browser = playwright.firefox.launch(headless=False)
    page = browser.new_page()
    page.goto("https://rahulshettyacademy.com/loginpagePractise")
    page.get_by_label("Username:").fill("rahulshettyacademy")
    page.get_by_label("Password:").fill("Learning@830$3mK2")
    page.get_by_role("combobox").select_option("teach")
    page.locator("#terms").check() # you can also use click()
    time.sleep(3)
    page.locator("#signInBtn").click()
    time.sleep(10)