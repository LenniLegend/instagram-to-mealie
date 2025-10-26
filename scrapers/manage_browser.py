import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from logs import setup_logging

logger = setup_logging("manage_browser")

def open_browser(url=None, platform=None):
    """
    Opens a browser window and navigates to the specified URL.
    If no URL is provided, navigates to Duck AI website.
    
    Args:
        url (str, optional): URL to navigate to. Defaults to Duck.ai.
        platform (str, optional): Platform type ("instagram", "tiktok") for specific handling.
    
    Returns:
        WebDriver: The browser window object.
    """
    
    logger.info(f"Opening browser{'for '+platform if platform else ''}")

    match os.getenv("BROWSER"):
        case "firefox":
            options = webdriver.FirefoxOptions()
            options.add_argument("--headless")
            browser = webdriver.Firefox(options=options) 
            logger.info("Using Firefox browser")
        case "chrome":
            options = webdriver.ChromeOptions()
            options.add_argument("--headless")
            browser = webdriver.Chrome(options=options)
            logger.info("Using Chrome browser")
        case "edge":
            options = webdriver.EdgeOptions()
            options.add_argument("--headless")
            browser = webdriver.Edge(options=options)
            logger.info("Using Edge browser")
        case "safari":
            options = webdriver.SafariOptions()
            options.add_argument("--headless")
            browser = webdriver.Safari(options=options)
            logger.info("Using Safari browser")
        case "docker":
            options = webdriver.FirefoxOptions()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            service = webdriver.firefox.service.Service(executable_path="/usr/local/bin/geckodriver")
            browser = webdriver.Firefox(options=options, service=service)
            logger.info("Using Firefox browser in Docker environment")
        case _:
            options = webdriver.FirefoxOptions()
            browser = webdriver.Firefox(options=options)
            logger.info("Using default Firefox browser")

    # Navigate to specified URL or Duck.ai
    target_url = url if url else "https://duck.ai/"
    logger.info(f"Navigating to {target_url}")
    browser.get(target_url)
    
    # Handle platform-specific setup
    if platform == "instagram" or platform == "i":
        try:
            logger.info("Waiting for Instagram overlay element to appear")
            WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "xzkaem6"))
            )
            div = browser.find_element(By.CLASS_NAME, "xzkaem6")
            browser.execute_script("arguments[0].style.visibility='hidden'", div)
            logger.info("Successfully hidden Instagram overlay")
        except Exception as e:
            logger.info(f"Failed to hide Instagram overlay: {e}")
    
    # If Duck.ai, handle welcome screens
    elif not url or "duck.ai" in target_url:
        logger.info("Navigating directly to Duck.ai chat page")
        
        try:
            # Direkt zur Chat-Seite navigieren (überspringt Welcome-Screen)
            browser.get('https://duck.ai/chat')
            time.sleep(3)  # Warte auf vollständiges Laden
            
            # Prüfe ob Chat-Interface geladen ist
            chat_input = WebDriverWait(browser, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "textarea, input[type='text']"))
            )
            logger.info("Chat interface loaded successfully")
            
        except TimeoutException:
            logger.warning("Chat interface not found - trying alternative selectors")
            try:
                # Alternative: Suche nach beliebigem Input-Feld
                chat_input = WebDriverWait(browser, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "textarea"))
                )
                logger.info("Chat interface loaded via alternative selector")
            except TimeoutException:
                logger.error("Failed to load Duck.ai chat interface")
                raise Exception("Failed to open browser - Duck.ai chat interface not accessible")
        
        except Exception as e:
            logger.error(f"Error accessing Duck.ai: {str(e)}")
            raise Exception("Failed to open browser")
    
    # General wait for content to load
    time.sleep(0.5)
    
    logger.info("Browser initialized successfully")
    return browser
        
def close_browser(browser):
    """
    Closes the browser window.
    Args:
        browser (WebDriver): The browser window object to close.
    """
    
    if browser:
        logger.info("Closing browser...")
        try:
            browser.quit()
        except Exception as e:
            logger.error(f"Error closing browser: {e}")

def capture_thumbnail(browser):
    """
    Attempts to capture a video thumbnail from the current page.
    
    Args:
        browser (WebDriver): The browser window object.
    
    Returns:
        str or None: Path to the thumbnail file if successful, otherwise None.
    """
    if os.getenv("BROWSER") != "docker":
        try:
            logger.info("Attempting to capture video thumbnail")
            # Create thumbnails directory if it doesn't exist
            os.makedirs('thumbnails', exist_ok=True)
            
            # Generate a unique filename
            thumbnail_filename = f"thumbnails/thumbnail_{int(time.time())}.png"
            
            # Wait for video element to be present
            logger.info("Waiting for video element")
            WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "video"))
            )
            
            # Find the video element
            video = browser.find_element(By.TAG_NAME, "video")
            
            # Take screenshot of the video element
            video.screenshot(thumbnail_filename)
            logger.info(f"Thumbnail saved to {thumbnail_filename}")
            return thumbnail_filename
        except Exception as e:
            logger.info(f"Failed to capture thumbnail: {e}")
            return None
    else: 
        logger.info("Skipping thumbnail capture in Docker environment")
        return None
