import json
import os
import re
import time
from bs4 import BeautifulSoup
from logs import setup_logging
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logger = setup_logging("duck_ai")


def initialize_chat(browser, caption):
    """
    Initialize a chat with Duck.ai by providing the recipe caption as context.
    
    Args:
        browser (WebDriver): The browser window object.
        caption (str): The recipe caption to use as context.
    
    Returns:
        bool: True if initialization is successful, False otherwise.
    """
    logger.info("Initializing chat with recipe context...")

    try:
        textarea = WebDriverWait(browser, 20).until(
            EC.presence_of_element_located((By.XPATH, "//textarea[@name='user-prompt']"))
        )

        # Sicherstellen, dass das Textfeld sichtbar und fokusiert ist
        browser.execute_script("arguments[0].scrollIntoView(true);", textarea)
        browser.execute_script("arguments[0].focus();", textarea)
        time.sleep(0.3)
        textarea.click()

        context_prompt = (
            f"I'm going to ask you questions about this recipe. "
            f"Please use this recipe information as context for all your responses: {caption}"
        )

        # Versuch 1: send_keys (falls Selenium Zugriff hat)
        try:
            textarea.clear()
            textarea.send_keys(context_prompt)
            textarea.send_keys(Keys.RETURN)
            logger.info("Prompt entered with send_keys()")
        except Exception:
            # Fallback: mit JavaScript schreiben
            browser.execute_script(
                "arguments[0].value = arguments[1]; "
                "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
                textarea,
                context_prompt,
            )
            logger.info("Prompt entered via JavaScript")
            browser.execute_script(
                "arguments[0].dispatchEvent(new KeyboardEvent('keydown', "
                "{ key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true }));",
                textarea,
            )

        # Warte kurz, bis Duck.ai reagiert
        time.sleep(2)

        try:
            # Fallback: Submit-Button klicken falls vorhanden
            submit = WebDriverWait(browser, 5).until(
                EC.presence_of_element_located((By.XPATH, "//button[@type='submit']"))
            )
            browser.execute_script("arguments[0].click();", submit)
            logger.info("Submit button clicked via JavaScript")
        except Exception:
            pass

        # Warten bis der Chat reagiert
        WebDriverWait(browser, 30).until_not(
            EC.presence_of_element_located((By.XPATH, "//button[@type='submit' and @disabled]"))
        )

        logger.info("Chat initialized successfully with recipe context")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize chat: {e}", exc_info=True)
        return False


def send_raw_prompt(browser, prompt):
    logger.info(f"Sending raw prompt: {prompt[:60]}...")
    try:
        textarea = WebDriverWait(browser, 15).until(
            EC.presence_of_element_located((By.XPATH, "//textarea[@name='user-prompt']"))
        )
        browser.execute_script("arguments[0].scrollIntoView(true);", textarea)
        browser.execute_script("arguments[0].focus();", textarea)
        time.sleep(0.3)

        browser.execute_script("arguments[0].value = '';", textarea)
        time.sleep(0.3)

        # Schreiben per JavaScript
        browser.execute_script(
            "arguments[0].value = arguments[1]; "
            "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
            textarea,
            prompt,
        )
        logger.info(f"Prompt entered via JavaScript ({len(prompt)} chars)")

        # Enter triggern
        browser.execute_script(
            "arguments[0].dispatchEvent(new KeyboardEvent('keydown', "
            "{ key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true }));",
            textarea,
        )

        # Fallback: Send button
        try:
            submit = WebDriverWait(browser, 3).until(
                EC.presence_of_element_located((By.XPATH, "//button[@type='submit']"))
            )
            browser.execute_script("arguments[0].click();", submit)
        except:
            logger.debug("No submit button found")

        # Warten bis Textarea wieder aktiv ist
        WebDriverWait(browser, 60).until(
            EC.element_to_be_clickable((By.XPATH, "//textarea[@name='user-prompt']"))
        )

        return browser.page_source

    except Exception as e:
        logger.error(f"Failed to send prompt: {e}", exc_info=True)
        return None


def extract_json_from_response(response):
    if not response:
        return None
    try:
        soup = BeautifulSoup(response, "html.parser")
        code_blocks = soup.find_all("code", {"class": "language-json"})
        if not code_blocks:
            logger.warning("No JSON block found in response")
            return None
        return json.loads(code_blocks[-1].get_text())
    except Exception as e:
        logger.error(f"Failed to parse JSON: {e}", exc_info=True)
        return None


def send_json_prompt(browser, prompt):
    response = send_raw_prompt(browser, prompt)
    return extract_json_from_response(response)


def get_number_of_steps(browser, caption=None):
    try:
        prompt = "How many steps are in this recipe? Please respond with only a number."
        response = send_raw_prompt(browser, prompt)
        if not response:
            logger.warning("No response received from Duck.ai")
            return None

        soup = BeautifulSoup(response, "html.parser")
        last = soup.find_all("div", {"class": "VrBPSncUavA1d7C9kAc5"})
        if not last:
            logger.warning("Couldn't find response divs")
            return None
        paragraph = last[-1].find("p")
        if not paragraph:
            return None

        text = paragraph.get_text().strip()
        digits = re.findall(r"\d+", text)
        return int(digits[0]) if digits else None

    except Exception as e:
        logger.error(f"Error extracting steps count: {e}", exc_info=True)
        return None


def process_recipe_part(browser, part, mode="", step_number=None):
    try:
        backticks = chr(96) * 3
        lang = os.getenv("LANGUAGE_CODE", "en")

        if mode == "step" or step_number is not None:
            prompt = (
                f"Write your Response in the language {lang}. "
                f"Please fill the JSON document {part}. "
                f"Only step {step_number}. Output enclosed in ({backticks}json)."
            )
        else:
            prompt = (
                f"Write your Response in {lang}. Fill JSON {part}. "
                f"Respond in JSON block ({backticks}json)."
            )

        data = send_json_prompt(browser, prompt)
        return data if data else None

    except Exception as e:
        logger.error(f"Error processing recipe part: {e}", exc_info=True)
        return None
