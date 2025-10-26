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
        # Try primary Shadow DOM selector (new: <duck-chat>)
        host = None
        try:
            host = WebDriverWait(browser, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "duck-chat"))
            )
            shadow_root = host.shadow_root
        except Exception:
            # Fallback: sometimes Duck.ai uses a different host element
            logger.info("Primary duck-chat host not found, trying fallback selectors")
            shadow_root = None

        # Helper to write debug HTML
        def _write_debug_html(prefix="init_chat"):
            try:
                src = browser.page_source
                fname = f"./scrapers/debug_{prefix}_{int(time.time())}.html"
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(src)
                logger.info(f"Wrote debug HTML to {fname}")
            except Exception as ex:
                logger.error(f"Failed to write debug HTML: {ex}")

        # If we have a shadow_root, prefer it
        textarea = None
        if shadow_root is not None:
            try:
                # prefer the explicitly named input
                candidates = shadow_root.find_elements(By.CSS_SELECTOR, "textarea[name='user-prompt'], textarea, input[type='text']")
                logger.info(f"Found {len(candidates)} candidate inputs in shadow root")
            except Exception:
                logger.info("No candidates inside shadow root - will try light DOM selectors")
                candidates = []
        else:
            candidates = []

        # Fallback: look in light DOM if no shadow candidates
        if not candidates:
            try:
                candidates = browser.find_elements(By.CSS_SELECTOR, "textarea[name='user-prompt'], textarea, input[type='text']")
                logger.info(f"Found {len(candidates)} candidate inputs in light DOM")
            except Exception as e:
                logger.error(f"Unable to locate any chat input candidates: {e}", exc_info=True)
                _write_debug_html("no_input")
                return False

        # Helper to check visibility using computed styles
        def _is_visible(el):
            try:
                return browser.execute_script(
                    "return (arguments[0] && arguments[0].offsetWidth>0 && arguments[0].offsetHeight>0 && window.getComputedStyle(arguments[0]).visibility !== 'hidden' && window.getComputedStyle(arguments[0]).display !== 'none');",
                    el,
                )
            except Exception:
                return False

        # Filter candidates for visible and not the known hidden state field
        visible_candidates = [c for c in candidates if _is_visible(c) and (c.get_attribute('id') or '').lower() != 'state_hidden' and (c.get_attribute('name') or '').lower() != 'state_hidden']
        logger.info(f"Filtered to {len(visible_candidates)} visible candidate inputs")

        if not visible_candidates:
            logger.error("No visible chat input found among candidates")
            _write_debug_html("no_visible_input")
            return False

        textarea = visible_candidates[0]

        # Focus and set value via JS rather than clicking (avoids ElementNotInteractable)
        try:
            context_prompt = (
                f"I'm going to ask you questions about this recipe. "
                f"Please use this recipe information as context for all your responses: {caption}"
            )

            # Ensure element is scrolled into view if possible, but ignore errors
            try:
                browser.execute_script("arguments[0].scrollIntoView({block:'center'});", textarea)
            except Exception:
                logger.info("scrollIntoView failed or not needed for selected element")

            # Use JS to focus and set the value
            browser.execute_script("arguments[0].focus();", textarea)
            time.sleep(0.1)
            browser.execute_script(
                "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new InputEvent('input', {bubbles: true, composed: true}));",
                textarea,
                context_prompt,
            )
            logger.info("Prompt filled successfully (shadow or light DOM)")

            # Try to click a submit button inside shadow root first, then fallback to light DOM
            send_button = None
            try:
                if shadow_root is not None:
                    send_button = shadow_root.find_element(By.CSS_SELECTOR, "button[type='submit']")
            except Exception:
                send_button = None

            if send_button is None:
                try:
                    send_button = browser.find_element(By.CSS_SELECTOR, "button[type='submit'], button[data-role='send']")
                except Exception:
                    send_button = None

            if send_button is None:
                logger.error("No send/submit button found to initialize chat")
                _write_debug_html("no_send_button")
                return False

            browser.execute_script("arguments[0].click();", send_button)

            # Wait for the send button to become enabled/disabled cycle (submit complete)
            try:
                WebDriverWait(browser, 30).until_not(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "button[type='submit'][disabled]"))
                )
            except Exception:
                # Not critical; proceed but write debug
                logger.info("Timeout waiting for submit button state change (continuing)")

            logger.info("Chat initialized successfully with recipe context")
            return True

        except Exception as e:
            logger.error(f"Failed while filling or submitting chat prompt: {e}", exc_info=True)
            _write_debug_html("fill_submit_error")
            return False

    except Exception as e:
        logger.error(f"Failed to initialize chat: {e}", exc_info=True)
        try:
            # best-effort debug dump
            with open('./scrapers/debug_init_chat.html', 'w', encoding='utf-8') as f:
                f.write(browser.page_source)
            logger.info("Wrote fallback debug HTML to ./scrapers/debug_init_chat.html")
        except Exception:
            logger.error("Failed to write fallback debug HTML")
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
        # 1) JSON code blocks (preferred)
        block = soup.find_all("code", {"class": "language-json"})
        if block:
            try:
                data = json.loads(block[-1].get_text())
                return data
            except Exception:
                logger.info("Found language-json code block but failed to parse as JSON, falling back")

        # 2) <pre> blocks that may contain JSON
        pres = soup.find_all("pre")
        for p in pres:
            text = p.get_text(strip=True)
            if text.startswith('{') or text.startswith('['):
                try:
                    return json.loads(text)
                except Exception:
                    continue

        # 3) triple-backtick fenced blocks in raw HTML/text
        full_text = soup.get_text("\n")
        backtick_blocks = re.findall(r"```(?:json\n)?([\s\S]*?)```", full_text, flags=re.IGNORECASE)
        for blk in backtick_blocks:
            try:
                return json.loads(blk.strip())
            except Exception:
                continue

        # 4) Fallback: regex search for JSON-like substrings and try to parse them
        candidates = re.findall(r"\{[\s\S]*?\}", full_text)
        # try longer candidates first
        candidates = sorted(candidates, key=lambda s: -len(s))
        for cand in candidates:
            try:
                return json.loads(cand)
            except Exception:
                continue

        logger.warning("No JSON block found in AI response after fallbacks")
        return None
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
                f"Return valid JSON enclosed in triple backticks ({backticks}json). "
                f"Respond ONLY with the JSON code block and no additional text."
            )
        elif mode == "info":
            prompt = (
                f"Write your Response in {lang}. "
                f"Fill author, description, recipeYield, prepTime, cookTime in {part}. "
                f"Return a single JSON code block containing exactly these keys. "
                f"Times must use ISO‑8601 duration format (PT30M, PT1H). "
                f"Respond ONLY with the JSON code block and nothing else."
            )
        elif mode == "ingredients":
            prompt = (
                f"Write your Response in {lang}. "
                f"Append all clearly mentioned ingredients to 'recipeIngredient' in {part}. "
                f"Return exactly a JSON code block like {{\"recipeIngredient\": [ ... ]}} and nothing else."
            )
        elif mode == "name":
            prompt = (
                f"Respond in {lang}. "
                f"Provide a concise title for this recipe in {part}. "
                f"Return exactly a JSON code block like {{\"name\": \"...\"}} and nothing else."
            )
        elif mode == "nutrition":
            prompt = (
                f"Respond in {lang}. "
                f"Fill calories and fatContent as strings in {part}. "
                f"Return exactly a JSON code block like {{\"nutrition\": {{...}}}} and nothing else."
            )
        else:
            prompt = (
                f"Write your Response in {lang}. "
                f"Complete JSON fragment {part}. "
                f"Ensure response is a single JSON code block in ({backticks}json) and nothing else."
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
