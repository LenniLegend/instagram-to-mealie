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
        textarea = WebDriverWait(browser, 15).until(
            EC.presence_of_element_located((By.XPATH, "//textarea[@name='user-prompt']"))
        )

        context_prompt = (
            f"I'm going to ask you questions about this recipe. "
            f"Please use this recipe information as context for all your responses: {caption}"
        )

        time.sleep(1)
        browser.execute_script(
            "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
            textarea, context_prompt
        )
        logger.info(f"Prompt entered via JavaScript ({len(context_prompt)} chars)")

        time.sleep(0.5)
        browser.execute_script(
            "arguments[0].dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));",
            textarea
        )

        try:
            submit_button = WebDriverWait(browser, 5).until(
                EC.presence_of_element_located((By.XPATH, "//button[@type='submit']"))
            )
            browser.execute_script("arguments[0].click();", submit_button)
            logger.info("Submit button clicked via JavaScript")
        except:
            logger.info("No submit button found, relying on Enter key event")

        time.sleep(3)
        WebDriverWait(browser, 60).until(
            EC.presence_of_element_located((By.XPATH, "//button[@type='submit' and @disabled]"))
        )
        WebDriverWait(browser, 60).until_not(
            EC.presence_of_element_located((By.XPATH, "//button//rect[@width='10' and @height='10']"))
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
        WebDriverWait(browser, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//textarea[@name='user-prompt']"))
        )

        browser.execute_script("arguments[0].value = '';", textarea)
        time.sleep(0.3)

        browser.execute_script(
            "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
            textarea, prompt
        )

        browser.execute_script(
            "arguments[0].dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));",
            textarea
        )

        try:
            submit_button = WebDriverWait(browser, 3).until(
                EC.presence_of_element_located((By.XPATH, "//button[@type='submit']"))
            )
            browser.execute_script("arguments[0].click();", submit_button)
        except:
            logger.info("Submit button not found, Enter key event used")

        WebDriverWait(browser, 60).until(
            EC.element_to_be_clickable((By.XPATH, "//textarea[@name='user-prompt']"))
        )
        logger.info("Response received successfully")
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
        json_data = code_blocks[-1].get_text()
        return json.loads(json_data)
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
        last_response = soup.find_all("div", {"class": "VrBPSncUavA1d7C9kAc5"})
        if not last_response:
            logger.warning("Could not find response container")
            return None

        paragraph = last_response[-1].find("p")
        if not paragraph:
            logger.warning("No paragraph found in response")
            return None

        text = paragraph.get_text().strip()
        digits = re.findall(r"\d+", text)
        if digits:
            count = int(digits[0])
            logger.info(f"Detected {count} recipe steps")
            return count
        logger.warning(f"No numeric value found in text: {text}")
        return None

    except Exception as e:
        logger.error(f"Error extracting steps count: {e}", exc_info=True)
        return None


def process_recipe_part(browser, part, mode="", step_number=None):
    try:
        backticks = chr(96) * 3
        lang_code = os.getenv("LANGUAGE_CODE", "en")

        if mode == "step" or step_number is not None:
            prompt = (
                f"Write your Response in the language {lang_code}. "
                f"Please fill out this JSON document {part}. "
                f"Only complete step {step_number} of the recipe. "
                f"If there are more than 3 ingredients, include only the first 3. "
                f"Respond with a valid JSON enclosed in triple backticks ({backticks}json)."
            )
        elif mode == "info":
            prompt = (
                f"Write your Response in {lang_code}. "
                f"Fill out author, description, recipeYield, prepTime, and cookTime in {part}. "
                f"Use ISO 8601 duration format, e.g., PT1H or PT20M."
            )
        elif mode == "ingredients":
            prompt = (
                f"Write your Response in {lang_code}. "
                f"Append ingredients to the 'recipeIngredient' list in {part}. One ingredient per line."
            )
        elif mode == "name":
            prompt = (
                f"Write your Response in {lang_code}. "
                f"Fill the field 'name' in {part} with a short recipe title."
            )
        elif mode == "nutrition":
            prompt = (
                f"Respond in {lang_code}. "
                f"Fill out calories and fatContent values in {part} as strings."
            )
        elif mode == "instructions":
            prompt = (
                f"Write your Response in {lang_code}. "
                f"Fill instructions field in {part} with one long combined text. No JSON fragments."
            )
        else:
            prompt = (
                f"Write your Response in {lang_code}. "
                f"Please fill out fields in {part}. Respond with a JSON block enclosed in ({backticks}json)."
            )

        data = send_json_prompt(browser, prompt)
        if data:
            logger.info(f"Processed recipe part ({mode}) successfully.")
            return data
        logger.warning(f"No response for mode {mode}")
        return None

    except Exception as e:
        logger.error(f"Error processing recipe part ({mode}): {e}", exc_info=True)
        return None
