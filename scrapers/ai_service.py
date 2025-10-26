import json
import os
import re
import time
from bs4 import BeautifulSoup
from logs import setup_logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logger = setup_logging("duck_ai")

def initialize_chat(browser, caption):
    """
    Initialize chat with Duck.ai (Shadow DOM-compatible as of Oct 2025)
    """
    logger.info("Initializing chat with recipe context...")

    try:
        # Shadow DOM Host (new: <duck-chat> in Oct 2025)
        host = WebDriverWait(browser, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "duck-chat"))
        )
        shadow_root = host.shadow_root  # Selenium 4+ native method

        # Inner text area
        textarea = shadow_root.find_element(By.CSS_SELECTOR, "textarea[name='user-prompt']")
        browser.execute_script("arguments[0].scrollIntoView({block:'center'});", textarea)
        browser.execute_script("arguments[0].focus();", textarea)
        textarea.click()
        time.sleep(0.3)

        context_prompt = (
            f"I'm going to ask you questions about this recipe. "
            f"Please use this recipe information as context for all your responses: {caption}"
        )

        # Eingabetext per JS setzen (damit Input‑Event auch im ShadowContext feuert)
        browser.execute_script(
            """
            arguments[0].value = arguments[1];
            arguments[0].dispatchEvent(new InputEvent('input', {bubbles: true, composed: true}));
            """,
            textarea,
            context_prompt,
        )
        logger.info("Prompt filled successfully inside Shadow DOM")

        # Submit (Duck.ai benutzt <form> im ShadowRoot)
        send_button = shadow_root.find_element(By.CSS_SELECTOR, "button[type='submit']")
        browser.execute_script("arguments[0].click();", send_button)

        WebDriverWait(browser, 30).until_not(
            EC.presence_of_element_located((By.CSS_SELECTOR, "button[type='submit'][disabled]"))
        )
        logger.info("Chat initialized successfully with recipe context")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize chat: {e}", exc_info=True)
        return False


def send_raw_prompt(browser, prompt):
    """
    Send a text prompt to Duck.ai and return HTML response
    """
    logger.info(f"Sending raw prompt: {prompt[:80]}...")
    try:
        host = WebDriverWait(browser, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "duck-chat")))
        shadow_root = host.shadow_root

        textarea = shadow_root.find_element(By.CSS_SELECTOR, "textarea[name='user-prompt']")
        browser.execute_script("arguments[0].scrollIntoView({block:'center'});", textarea)
        browser.execute_script("arguments[0].focus();", textarea)
        time.sleep(0.3)

        browser.execute_script("arguments[0].value = '';", textarea)
        time.sleep(0.2)

        browser.execute_script(
            """
            arguments[0].value = arguments[1];
            arguments[0].dispatchEvent(new InputEvent('input', {bubbles: true, composed: true}));
            """,
            textarea,
            prompt,
        )

        send_button = shadow_root.find_element(By.CSS_SELECTOR, "button[type='submit']")
        browser.execute_script("arguments[0].click();", send_button)

        WebDriverWait(browser, 60).until_not(
            EC.presence_of_element_located((By.CSS_SELECTOR, "button[type='submit'][disabled]"))
        )

        response = browser.page_source
        logger.info("Prompt sent and response retrieved successfully")
        return response

    except Exception as e:
        logger.error(f"Failed to send prompt: {e}", exc_info=True)
        return None


def extract_json_from_response(response):
    """
    Extract structured JSON result from Duck.ai HTML output
    """
    if not response:
        return None
    try:
        soup = BeautifulSoup(response, "html.parser")
        block = soup.find_all("code", {"class": "language-json"})
        if not block:
            logger.warning("No JSON block found in AI response")
            return None
        data = json.loads(block[-1].get_text())
        return data
    except Exception as e:
        logger.error(f"Failed to extract JSON from AI response: {e}", exc_info=True)
        return None


def send_json_prompt(browser, prompt):
    """Wrapper: send prompt and parse JSON response"""
    return extract_json_from_response(send_raw_prompt(browser, prompt))


def get_number_of_steps(browser, caption=None):
    """
    Ask Duck.ai to count recipe steps from current chat context
    """
    logger.info("Querying number of steps...")
    try:
        prompt = "How many cooking steps are in this recipe? Respond only with the number."
        html = send_raw_prompt(browser, prompt)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        text_nodes = soup.find_all("p")
        numbers = re.findall(r"\d+", " ".join([p.text for p in text_nodes]))
        if numbers:
            steps = int(numbers[0])
            logger.info(f"Detected {steps} cooking steps.")
            return steps
        return None
    except Exception as e:
        logger.error(f"Error determining number of steps: {e}", exc_info=True)
        return None


def process_recipe_part(browser, part, mode="", step_number=None):
    """
    Build and send prompt to Duck.ai to extract recipe sub-sections in JSON
    """
    try:
        backticks = chr(96) * 3
        lang = os.getenv("LANGUAGE_CODE", "en")

        if mode == "step" and step_number is not None:
            prompt = (
                f"Write your Response in {lang}. "
                f"Fill the following JSON section {part}. "
                f"Only cover cooking step {step_number}. Limit to 3 ingredients. "
                f"Return valid JSON enclosed in triple backticks ({backticks}json)."
            )
        elif mode == "info":
            prompt = (
                f"Write your Response in {lang}. "
                f"Fill author, description, recipeYield, prepTime, cookTime in {part}. "
                f"Times must use ISO‑8601 duration format (PT30M, PT1H)."
            )
        elif mode == "ingredients":
            prompt = (
                f"Write your Response in {lang}. "
                f"Append all clearly mentioned ingredients to 'recipeIngredient' in {part}."
            )
        elif mode == "name":
            prompt = (
                f"Respond in {lang}. "
                f"Provide a concise title for this recipe in {part}."
            )
        elif mode == "nutrition":
            prompt = (
                f"Respond in {lang}. "
                f"Fill calories and fatContent as strings in {part}."
            )
        else:
            prompt = (
                f"Write your Response in {lang}. "
                f"Complete JSON fragment {part}. "
                f"Ensure response is a JSON code block in ({backticks}json)."
            )

        data = send_json_prompt(browser, prompt)
        if data:
            logger.info(f"Processed recipe part '{mode}' successfully.")
        else:
            logger.warning(f"No valid response for mode '{mode}'.")
        return data

    except Exception as e:
        logger.error(f"Error processing recipe part '{mode}': {e}", exc_info=True)
        return None
