import json
from datetime import datetime

from logs import setup_logging
from scrapers.ai_service import initialize_chat, process_recipe_part
from scrapers.api_service import send_recipe
from scrapers.manage_browser import open_browser, close_browser
from scrapers.social_scraper import get_caption_from_post

logger = setup_logging("scrape_for_mealie")

def scrape_recipe_for_mealie(url, platform):
    """
    Function to process a social media post URL and extract recipe information.
    Uses a single browser instance for all Duck.ai interactions.
    
    Args:
        url (str): The URL of the social media post containing the recipe.
        platform (str): The platform ('instagram' or 'tiktok').
    
    Returns:
        dict: Result information including URL and status.
        
    Raises:
        Exception: If processing fails.
    """
    
    result = get_caption_from_post(url, platform)
    
    if result is None:
        logger.error("No caption or image found")
        raise Exception("No caption or image found")
    
    caption, thumbnail_filename = result
    logger.info(f"Caption extracted successfully ({len(caption)} chars)")
    
    # Open a single browser instance that will be used for all Duck.ai interactions
    browser = open_browser()
    if not browser:
        logger.error("Failed to open browser")
        raise Exception("Failed to open browser")
    
    try:
        # Initialize chat with the recipe caption to establish context
        if not initialize_chat(browser, caption):
            logger.error("Failed to initialize chat with recipe context")
            raise Exception("Failed to initialize chat with recipe context")
        
        json_parts = [
            {
                "@context": "https://schema.org",
                "@type": "Recipe",
                "author": "string",
                "cookTime": "PT1H",
                "prepTime": "PT15M",
                "datePublished": "string",
                "description": "",
                "image": None,
                "recipeYield": "",
            },
            {
                "recipeIngredient": [
                    "string",
                ],
            },
            {
                "interactionStatistic": 
                    {
                        "@type": "InteractionCounter",
                        "interactionType": "https://schema.org/Comment",
                        "userInteractionCount": "140"
                    },
            },
            {
                "name": "",
            },
            {
                "nutrition": {
                    "@type": "NutritionInformation",
                    "calories": "string",
                    "fatContent": "string"
                },
            },
            {
                "suitableForDiet": None
            },
            {
                "recipeInstructions": "string",
            }
        ]
    
        # Build the recipe JSON structure
        full_json = {}
        
        # Get recipe instructions
        logger.info("Getting recipe instructions")
        instructions_res = process_recipe_part(browser, json_parts[6], "instructions")
        if instructions_res:
            full_json.update(instructions_res)
            logger.info("Recipe instructions processed successfully")
        else:
            logger.warning("Failed to get recipe instructions")
        
        # Get recipe general information
        logger.info("Getting recipe information")
        info_res = process_recipe_part(browser, json_parts[0], "info")
        if info_res:
            full_json.update(info_res)
            logger.info("Recipe information processed successfully")
        else:
            logger.warning("Failed to get recipe information")
        
        # Get recipe ingredients
        logger.info("Getting recipe ingredients")
        ingredients_res = process_recipe_part(browser, json_parts[1], "ingredients")
        if ingredients_res:
            full_json.update(ingredients_res)
            logger.info("Recipe ingredients processed successfully")
        else:
            logger.warning("Failed to get recipe ingredients")
        
        # Add interaction statistics
        full_json.update(json_parts[2])
        
        # Get recipe name
        logger.info("Getting recipe name")
        name_res = process_recipe_part(browser, json_parts[3], "name")
        if name_res:
            full_json.update(name_res)
            logger.info(f"Recipe name: {name_res.get('name', 'Unknown')}")
        else:
            logger.warning("Failed to get recipe name")
        
        # Get nutrition information
        logger.info("Getting nutrition information")
        nutrition_res = process_recipe_part(browser, json_parts[4], "nutrition")
        if nutrition_res:
            full_json.update(nutrition_res)
            logger.info("Nutrition information processed successfully")
        else:
            logger.warning("Failed to get nutrition information")
        
        # Add diet suitability
        full_json.update(json_parts[5])
        
        # Add current date
        full_json["datePublished"] = datetime.now().strftime("%Y-%m-%d")
        
        # Format as JSON-LD script
        json_ld_script = f'<script type="application/ld+json">{json.dumps(full_json)}</script>'
        
        # Create final JSON structure for Mealie API
        final_json = {
            "includeTags": False,
            "data": json_ld_script
        }
                        
        logger.info("Saving final JSON")
        with open('./scrapers/final_json.json', 'w') as outfile:
            json.dump(final_json, outfile, indent=2)
        
        # Send to Mealie
        logger.info("Sending to Mealie API")
        mealie_result = send_recipe("MEALIE", final_json, thumbnail_filename)
        
        return {
            "url": url,
            "status": "success",
            "result": mealie_result
        }
        
    except Exception as e:
        logger.error(f"Error processing recipe: {e}", exc_info=True)
        raise
    
    finally:
        # Always close the browser
        close_browser(browser)