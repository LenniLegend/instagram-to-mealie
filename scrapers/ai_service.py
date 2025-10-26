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


def _save_debug_artifacts(browser, prefix):
    """Save page_source, a screenshot and browser console logs for offline inspection.

    Best-effort helper: any failure is ignored so this never raises during normal runs.
    """
    ts = int(time.time())
    try:
        src = browser.page_source
        fname = f"./scrapers/{prefix}_page_{ts}.html"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(src)
        logger.info(f"Wrote debug page_source to {fname}")
    except Exception as e:
        logger.debug(f"Failed to write debug page_source: {e}")
    try:
        screenshot = f"./scrapers/{prefix}_screenshot_{ts}.png"
        browser.save_screenshot(screenshot)
        logger.info(f"Wrote debug screenshot to {screenshot}")
    except Exception as e:
        logger.debug(f"Failed to write screenshot: {e}")
    try:
        # browser.get_log may not be supported in all environments; try best-effort
        logs = []
        try:
            logs = browser.get_log('browser')
        except Exception:
            # fallback: try driver.execute_script to read console if available
            try:
                logs = browser.execute_script('return window.__consoleLogs || []') or []
            except Exception:
                logs = []
        if logs:
            logfile = f"./scrapers/{prefix}_console_{ts}.json"
            with open(logfile, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
            logger.info(f"Wrote browser console logs to {logfile}")
    except Exception as e:
        logger.debug(f"Failed to save console logs: {e}")



def initialize_chat(browser, caption):
    """
    Initialize a chat with Duck.ai by providing the recipe caption as context.
    Compatible with Duck.ai light DOM structure (Oct 2025).
    """
    logger.info("Initializing chat with recipe context...")

    try:
        # Versuche primär duck-chat im Shadow DOM
        try:
            host = WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "duck-chat"))
            )
            shadow_root = browser.execute_script("return arguments[0].shadowRoot;", host)
            textarea = browser.execute_script(
                "return arguments[0].querySelector('textarea[name=\"user-prompt\"]');",
                shadow_root
            )
            if textarea:
                logger.info("Found textarea in shadow DOM")
        except Exception:
            logger.info("Primary duck-chat host not found, trying fallback selectors")
            # save artifacts for debugging why host not found
            try:
                _save_debug_artifacts(browser, 'init_no_duckchat')
            except Exception:
                pass
            textarea = None

        # Fallback: Suche nach Textarea im normalen DOM
        if not textarea:
            candidates = browser.find_elements(By.CSS_SELECTOR, "textarea")
            logger.info(f"Found {len(candidates)} candidate textareas in light DOM")
            
            visible_candidates = []
            for idx, elem in enumerate(candidates):
                try:
                    if elem.is_displayed():
                        visible_candidates.append(elem)
                except:
                    pass
            
            logger.info(f"Filtered to {len(visible_candidates)} visible candidate textareas")
            
            if not visible_candidates:
                # debug artifacts
                try:
                    _save_debug_artifacts(browser, 'init_no_visible_input')
                except Exception:
                    pass
                raise Exception("No visible textarea found for chat input")
            
            textarea = visible_candidates[0]

        # Text eingeben
        browser.execute_script("arguments[0].scrollIntoView({block:'center'});", textarea)
        browser.execute_script("arguments[0].focus();", textarea)
        time.sleep(0.5)

        context_prompt = (
            f"I'm going to ask you questions about this recipe. "
            f"Please use this recipe information as context for all your responses: {caption}"
        )

        browser.execute_script(
            "arguments[0].value = arguments[1]; "
            "arguments[0].dispatchEvent(new Event('input', {bubbles:true, composed:true}));",
            textarea,
            context_prompt
        )
        
        time.sleep(0.5)
        
        # Submit via Enter oder Button
        try:
            browser.execute_script(
                "arguments[0].dispatchEvent(new KeyboardEvent('keydown', "
                "{key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true, composed:true}));",
                textarea
            )
        except:
            pass

        # Fallback: Submit-Button
        try:
            submit = browser.find_element(By.CSS_SELECTOR, "button[type='submit']")
            browser.execute_script("arguments[0].click();", submit)
        except:
            pass

        logger.info("Prompt filled successfully (shadow or light DOM)")
        
        # Warte auf Antwort - längere Zeit
        time.sleep(5)
        
        logger.info("Chat initialized successfully with recipe context")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize chat: {e}", exc_info=True)
        return False


def send_raw_prompt(browser, prompt):
    """
    Send a prompt to Duck.ai and get the raw HTML response.
    """
    logger.info(f"Sending raw prompt: {prompt[:80]}...")
    
    try:
        # Warte kurz vor jedem neuen Prompt
        time.sleep(2)
        
        # Versuche primär Shadow DOM
        textarea = None
        try:
            host = browser.find_element(By.CSS_SELECTOR, "duck-chat")
            shadow_root = browser.execute_script("return arguments[0].shadowRoot;", host)
            textarea = browser.execute_script(
                "return arguments[0].querySelector('textarea[name=\"user-prompt\"]');",
                shadow_root
            )
        except Exception:
            logger.info("duck-chat host not found in send_raw_prompt, will try light DOM selectors")
            try:
                _save_debug_artifacts(browser, 'send_no_duckchat')
            except Exception:
                pass

        # Fallback: Light DOM - NUR Textareas (nicht input!)
        if not textarea:
            candidates = browser.find_elements(By.CSS_SELECTOR, "textarea")
            logger.info(f"send_raw_prompt found {len(candidates)} textareas in light DOM")
            
            # Debug: Speichere Kandidaten-Info
            debug_data = []
            for idx, elem in enumerate(candidates):
                try:
                    is_visible = elem.is_displayed()
                    debug_data.append({
                        "index": idx,
                        "tag": elem.tag_name,
                        "id": elem.get_attribute("id") or "",
                        "name": elem.get_attribute("name") or "",
                        "classes": elem.get_attribute("class") or "",
                        "placeholder": elem.get_attribute("placeholder") or "",
                        "visible": is_visible
                    })
                except:
                    pass
            
            # Wähle sichtbare Textarea
            visible = [c for c in candidates if c.is_displayed()]
            
            if not visible:
                # Debug-Ausgabe
                import time as t
                debug_file = f"./scrapers/debug_candidates_{int(t.time())}.json"
                with open(debug_file, "w") as f:
                    json.dump(debug_data, f, indent=2)
                logger.info(f"Wrote textarea candidate diagnostics to {debug_file}")
                
                logger.error("No visible textarea candidate in send_raw_prompt")
                
                # Letzter Fallback: Nimm erste Textarea auch wenn nicht visible
                if candidates:
                    textarea = candidates[0]
                    logger.info("Attempting forced input set on first textarea (may not be visible)")
                else:
                    try:
                        _save_debug_artifacts(browser, 'send_no_visible_candidates')
                    except Exception:
                        pass
                    return None
            else:
                textarea = visible[0]

        # Text eingeben
        browser.execute_script("arguments[0].scrollIntoView({block:'center'});", textarea)
        browser.execute_script("arguments[0].focus();", textarea)
        time.sleep(0.3)
        
        browser.execute_script("arguments[0].value = '';", textarea)
        time.sleep(0.3)

        browser.execute_script(
            "arguments[0].value = arguments[1]; "
            "arguments[0].dispatchEvent(new Event('input', {bubbles:true, composed:true}));",
            textarea,
            prompt
        )

        time.sleep(0.5)
        
        # Submit
        try:
            browser.execute_script(
                "arguments[0].dispatchEvent(new KeyboardEvent('keydown', "
                "{key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true, composed:true}));",
                textarea
            )
        except:
            pass

        # Fallback: Button
        try:
            submit = browser.find_element(By.CSS_SELECTOR, "button[type='submit']")
            browser.execute_script("arguments[0].click();", submit)
        except:
            pass

        # Warte auf Antwort
        time.sleep(4)
        
        # Warte bis Submit-Button wieder aktiv ist (Antwort fertig)
        try:
            WebDriverWait(browser, 60).until(
                lambda d: not d.find_element(By.CSS_SELECTOR, "button[type='submit']").get_attribute("disabled")
            )
        except:
            pass

        logger.info("Prompt sent and response retrieved successfully")
        return browser.page_source

    except Exception as e:
        logger.error(f"Failed to send prompt: {e}", exc_info=True)
        return None


def extract_json_from_response(response):
    """
    Extract JSON from a Duck AI HTML response.
    """
    if not response:
        return None
        
    try:
        soup = BeautifulSoup(response, "html.parser")
        code_blocks = soup.find_all("code", {"class": "language-json"})
        
        if code_blocks:
            json_response = code_blocks[-1].get_text()
            return json.loads(json_response)
        else:
            logger.warning("No JSON block found in AI response after fallbacks")
            
            # Debug-Ausgabe
            import time as t
            debug_file = f"./scrapers/debug_no_json_{int(t.time())}.html"
            with open(debug_file, "w") as f:
                f.write(response)
            logger.info(f"Wrote debug AI response to {debug_file}")
            
            # Letzter Versuch: Suche JSON-ähnliche Struktur im Text
            logger.info("Attempting in-browser DOM traversal to find JSON candidates (shadow/iframe aware)")
            # Hier könnte man noch weitere Parsing-Versuche machen
            return None
            
    except Exception as e:
        logger.error(f"Failed to extract JSON: {e}", exc_info=True)
        return None


def send_json_prompt(browser, prompt):
    """
    Send a prompt to Duck AI and extract JSON from the response.
    """
    response = send_raw_prompt(browser, prompt)
    data = extract_json_from_response(response)
    if data is None:
        try:
            _save_debug_artifacts(browser, 'no_json')
        except Exception:
            pass
    return data


def get_number_of_steps(browser, caption=None):
    """
    Extracts the number of steps from a recipe caption using Duck.ai.
    """
    logger.info("Getting number of recipe steps...")
    
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
        
        if digits:
            count = int(digits[0])
            logger.info(f"Detected {count} recipe steps")
            return count
            
        return None

    except Exception as e:
        logger.error(f"Error extracting steps count: {e}", exc_info=True)
        return None


def process_recipe_part(browser, part, mode="", step_number=None):
    """
    Process a part of a recipe using Duck AI and get structured data.
    """
    try:
        backticks = chr(96) * 3
        lang = os.getenv("LANGUAGE_CODE", "en")

        if mode == "step" or step_number is not None:
            prompt = (
                f"Write your Response in the language {lang}. "
                f"Please fill the JSON document {part}. "
                f"Only step {step_number}. Return enclosed in ({backticks}json)."
            )
        elif mode == "info":
            prompt = (
                f"Write your Response in {lang}. "
                f"Fill author, description, recipeYield, prepTime, and cookTime in {part}. "
                f"Use ISO 8601 duration format. Return enclosed in ({backticks}json)."
            )
        elif mode == "ingredients":
            prompt = (
                f"Write your Response in {lang}. "
                f"Append all clearly mentioned ingredients to 'recipeIngredient' in {part}. "
                f"Return enclosed in ({backticks}json)."
            )
        elif mode == "name":
            prompt = (
                f"Respond in {lang}. "
                f"Provide a concise title for this recipe in {part}. "
                f"Return enclosed in ({backticks}json)."
            )
        elif mode == "nutrition":
            prompt = (
                f"Respond in {lang}. "
                f"Fill calories and fatContent as strings in {part}. "
                f"Return enclosed in ({backticks}json)."
            )
        elif mode == "instructions":
            prompt = (
                f"Write your Response in {lang}. "
                f"Complete JSON fragment {part}. "
                f"Return enclosed in ({backticks}json)."
            )
        else:
            prompt = (
                f"Write your Response in {lang}. "
                f"Fill JSON {part}. Return enclosed in ({backticks}json)."
            )

        data = send_json_prompt(browser, prompt)
        
        if data:
            logger.info(f"Processed recipe part ({mode}) successfully.")
        else:
            logger.warning(f"No valid response for mode '{mode}'.")
            
        return data

    except Exception as e:
        logger.error(f"Error processing recipe part '{mode}': {e}", exc_info=True)
        return None
