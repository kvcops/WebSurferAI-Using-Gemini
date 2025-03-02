import os
import time
import argparse
import json
import base64
from urllib.parse import urlparse, urljoin
from datetime import datetime
import uuid
from dotenv import load_dotenv
import logging
from playwright.sync_api import sync_playwright
from PIL import Image
from io import BytesIO
import google.generativeai as genai

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Configure Google Gemini API
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    API_KEY = "YOUR_API_KEY_HERE"  # Default API KEY
if API_KEY == "YOUR_API_KEY_HERE":
    logging.warning("Using default API key. Set your GEMINI_API_KEY in .env file for proper use.")

genai.configure(api_key=API_KEY)

# Initialize the Gemini model - using the visual model
MODEL_NAME = "gemini-2.0-flash-thinking-exp"  # "gemini-2.0-flash" or "gemini-1.0-pro-vision-001",  gemini-pro
model = genai.GenerativeModel(MODEL_NAME)

class AutonomousWebAssistant:
    def __init__(self, headless=False, debug=False, screenshot_dir="screenshots", memory_file="memory.json"):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.page = None  # Playwright Page object will be initialized in initialize_browser
        self.headless = headless
        self.debug = debug
        self.screenshot_dir = screenshot_dir
        self.screenshot_count = 0
        self.current_task = None
        self.task_history = []
        self.action_history = []
        self.memory_file = memory_file
        self.memory = self.load_memory()
        self.captcha_solving_active = False
        self.element_search_timeout = 10
        self.explored_urls = set()
        self.internal_monologue = []

        if not os.path.exists(self.screenshot_dir):
            os.makedirs(self.screenshot_dir)

        self.initialize_browser()

    def initialize_browser(self):
        """Initialize the Playwright browser and page."""
        if self.page:
            self.page.close() # Close existing page if any before creating new one
        self.page = self.browser.new_page()
        self.page.set_viewport_size({"width": 1920, "height": 1080}) # Consistent viewport size
        logging.info("Playwright browser initialized.")

    def load_memory(self):
        """Loads memory from the memory file."""
        try:
            with open(self.memory_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logging.info("Memory file not found or invalid. Starting with an empty memory.")
            return {}

    def save_memory(self):
        """Saves the current memory to the memory file."""
        try:
            with open(self.memory_file, 'w') as f:
                json.dump(self.memory, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving memory to file: {e}")

    def add_memory(self, key, value, category="general"):
        """Adds a new memory entry using UUIDs for unique keys."""
        memory_id = str(uuid.uuid4())
        self.memory[memory_id] = {
            "key": key,
            "value": value,
            "category": category,
            "timestamp": datetime.now().isoformat()
        }
        self.save_memory()
        return memory_id

    def retrieve_memory(self, key, category=None):
        """Retrieves memory entries based on key and optionally category."""
        results = []
        for mem_id, mem_data in self.memory.items():
            if mem_data['key'] == key and (category is None or mem_data['category'] == category):
                results.append(mem_data)
        return results

    def clear_memory(self, category=None):
        """Clears memory entries, optionally filtering by category."""
        if category:
            keys_to_delete = [mem_id for mem_id, mem_data in self.memory.items() if mem_data['category'] == category]
            for mem_id in keys_to_delete:
                del self.memory[mem_id]
        else:
            self.memory = {}
        self.save_memory()

    def close_browser(self):
        """Close the Playwright browser and context."""
        if self.browser:
            self.browser.close()
            self.playwright.stop()
            logging.info("Playwright browser closed.")

    def take_screenshot(self, filename=None):
        """Take a screenshot and save it, or return as bytes."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.screenshot_count += 1
        if filename is None:
            filename = f"{self.screenshot_dir}/screenshot_{timestamp}_{self.screenshot_count}.png"

        screenshot = self.page.screenshot() # Take screenshot using Playwright

        if filename:
            with open(filename, "wb") as f:
                f.write(screenshot)
            logging.info(f"📸 Screenshot saved: {filename}")
        return screenshot, filename

    def get_screenshot_as_base64(self):
        """Get the current screenshot as base64 string for API requests."""
        screenshot = self.page.screenshot()
        return base64.b64encode(screenshot).decode('utf-8')

    def execute_task(self, user_task):
        """Main method to process and execute a user task autonomously."""
        logging.info(f"🤖 Understanding task: {user_task}")
        self.current_task = user_task
        self.task_history.append(user_task)
        self.internal_monologue = []

        if not self.action_history or self.action_history[-1]['action'] == "TASK_COMPLETE":
            self.navigate_to_url("https://www.google.com")

        max_steps = 30
        current_step = 0
        exploration_depth = 2
        retry_attempts = 0
        max_retry_attempts = 3

        while current_step < max_steps:
            current_step += 1
            logging.info(f"\n🔄 Step {current_step}/{max_steps}: Taking screenshot and determining next action...")

            screenshot, filename = self.take_screenshot()

            next_action = self.get_next_action_from_gemini(screenshot, user_task, current_step)

            self.internal_monologue.append({
                "step": current_step,
                "gemini_reasoning": next_action.get("reasoning", "No reasoning provided"),
                "action": next_action["action"],
                "details": next_action.get("details", {}),
                "self_assessment": "Evaluating action..."
            })

            self.action_history.append({
                "step": current_step,
                "action": next_action["action"],
                "details": next_action.get("details", {}),
                "screenshot": filename
            })

            if next_action["action"] == "TASK_COMPLETE":
                logging.info(f"✅ Task completed: {next_action.get('message', 'Gemini determined the task is complete')}")
                break
            elif next_action["action"] == "MANUAL_CAPTCHA":
                logging.warning("🚨 Captcha detected! Pausing automation. Please solve the captcha manually in the browser.")
                self.captcha_solving_active = True
                input("Press Enter after you have solved the captcha...")
                self.captcha_solving_active = False
                logging.info("Resuming automation...")
                continue
            elif next_action["action"] == "EXPLORE_WEBSITE":
                logging.info("🌐 Initiating website exploration...")
                self.explore_website(url=self.page.url, max_depth=exploration_depth)
                logging.info("Exploration complete. Resuming task execution.")
                continue
            elif next_action["action"] == "RETRY":
                logging.info("🔄 Gemini suggested to retry the last action...")
                retry_attempts += 1
                if retry_attempts > max_retry_attempts:
                    logging.error(f"❌ Max retry attempts reached ({max_retry_attempts}).  Aborting.")
                    break
                continue
            else:
                retry_attempts = 0

            status = self.execute_action(next_action)
            self.internal_monologue[-1]["action_result"] = status

            if status.get("status") == "ERROR":
                logging.error(f"❌ Error executing action: {status.get('message')}")
                recovery_screenshot, _ = self.take_screenshot()
                recovery_action = self.get_recovery_action(recovery_screenshot, status.get("message"), user_task)

                if recovery_action["action"] == "ABORT":
                    logging.error("❌ Cannot recover from error, aborting task")
                    break

                self.internal_monologue[-1]["recovery_action"] = recovery_action
                recovery_status = self.execute_action(recovery_action)
                self.internal_monologue[-1]["recovery_result"] = recovery_status

                if recovery_status.get("status") == "ERROR":
                    logging.error(f"❌ Recovery action failed: {recovery_status.get('message')}. Aborting.")
                    break

            time.sleep(1)

        summary = self.generate_task_summary(user_task)
        logging.info("\n📊 Task Summary:")
        logging.info(summary)

        if self.debug:
            logging.info("\n🧠 Internal Monologue:")
            for thought in self.internal_monologue:
                logging.info(thought)

        return {
            "task": user_task,
            "steps": current_step,
            "actions": self.action_history,
            "summary": summary,
            "internal_monologue": self.internal_monologue
        }

    def get_next_action_from_gemini(self, screenshot, task, step_number):
        """Use Gemini to analyze screenshot and determine next action."""
        if isinstance(screenshot, bytes):
            image_bytes = screenshot
        else:
            with open(screenshot, "rb") as f:
                image_bytes = f.read()

        image_parts = [
            {
                "inline_data": {
                    "data": base64.b64encode(image_bytes).decode("utf-8"),
                    "mime_type": "image/png"
                }
            }
        ]

        relevant_memories = []
        relevant_memories.extend(list(self.memory.values())[-5:])
        relevant_memories.extend(self.retrieve_memory(key=urlparse(self.page.url).netloc, category="website"))

        memory_context = ""
        if relevant_memories:
            memory_context = "\n**Relevant Memories:**\n"
            for mem in relevant_memories:
                memory_context += f"- {mem['key']}: {mem['value']}\n"

        prompt = f"""
                You are an expert web automation assistant using Playwright.

                **Current Task:** {task}
                **Step Number:** {step_number}
                **Current URL:** {self.page.url}
                **Page Title:** {self.page.title()}
                **Previous Actions:** (Summarized) {self.summarize_action_history()}
                {memory_context}

                **Your Goal:** Autonomously complete the user's task by interacting with the webpage using Playwright.

                **Consider these capabilities and instructions when deciding the next action:**

                1.  **Task Understanding and Goal Decomposition:** Understand the overall task. Break it down into smaller steps.

                2.  **Website Exploration for Task Discovery (NEW FEATURE):** If needed for vague tasks, suggest action: "EXPLORE_WEBSITE".

                3.  **CAPTCHA Handling:** If CAPTCHA is visible, suggest "MANUAL_CAPTCHA".

                4.  **Action Selection Strategy:** Choose the MOST RELEVANT SINGLE NEXT ACTION.

                5.  **Element Identification (Playwright Locators):** For "CLICK" and "TYPE" actions, use robust Playwright locators:
                    *   Prioritize **text-based locators** (e.g., `"text=Submit"`, `"text='Log In'"`, `"text=exact:Search"`).
                    *   Use **CSS selectors** when text locators are insufficient (e.g., `"#id"`, `.class`, `"div > button"`).
                    *   Consider **role-based locators** for accessibility (e.g., `"[role='button']"`, `"getByRole('link', name='Learn more')"`).
                    *   For complex scenarios, use **chained locators** (e.g., `".parent >> .child"`).
                    *   If multiple elements match, use `:nth(index)` or `locator.nth(index)` to target a specific one.
                    *   Suggest the **most specific and reliable locator** in 'details'.
                    *   If text is reliable, use text locators. Otherwise, use CSS or other suitable locators.

                6.  **Recovery and Retry:** Suggest "action: RETRY" for transient errors.

                7.  **TASK_COMPLETE Recognition:** Suggest "action: TASK_COMPLETE" when the task is fulfilled.

                8. **Memory Utilization:** Use provided memories to inform decisions.

                **Output Format:** Return JSON object:
                {{
                  "action":  (CLICK, TYPE, NAVIGATE, SCROLL, WAIT, EXTRACT, TASK_COMPLETE, MANUAL_CAPTCHA, EXPLORE_WEBSITE, ABORT, RETRY)
                  "details": {{ ...action-specific details... }}
                  "reasoning": "Explain action choice."
                  "message": "User-friendly action description."
                }}
                **Examples:**
                {{"action": "CLICK", "details": {{"locator": "text=Sign In"}}, "reasoning": "User needs to log in", "message": "Clicking 'Sign In' button."}}
                {{"action": "TYPE", "details": {{"locator": "#search-query", "text": "product search"}}, "reasoning": "Searching for products", "message": "Typing 'product search' in search box."}}
                {{"action": "NAVIGATE", "details": {{"url": "https://example.com/pricing"}}, "reasoning": "Navigating to pricing page", "message": "Navigating to pricing page."}}
                {{"action": "TASK_COMPLETE", "reasoning": "Task completed", "message": "Task completed."}}
                {{"action": "MANUAL_CAPTCHA", "reasoning": "Captcha detected", "message": "Solve CAPTCHA manually."}}
                {{"action": "EXPLORE_WEBSITE", "details": {{}}, "reasoning": "Exploring website for testing", "message": "Initiating website exploration."}}
                {{"action": "RETRY", "reasoning": "Retrying last action", "message": "Retrying last action."}}

                **IMPORTANT:** Respond with JSON ONLY.
                """

        try:
            response = model.generate_content([prompt] + image_parts)
            response_text = response.text.strip()

            try:
                if response_text.startswith("```json"):
                    json_text = response_text.split("```json")[1].split("```")[0].strip()
                elif response_text.startswith("```"):
                    json_text = response_text.split("```")[1].strip()
                else:
                    json_text = response_text

                action_data = json.loads(json_text)

                logging.info(f"💭 Gemini's reasoning: {action_data.get('reasoning', 'No reasoning provided')}")
                logging.info(f"🚀 Next action: {action_data.get('message', action_data.get('action', 'Unknown action'))}")
                return action_data

            except json.JSONDecodeError as e:
                logging.error(f"❌ Error parsing Gemini response as JSON: {e}")
                logging.error(f"Response text: {response_text}")
                return {
                    "action": "WAIT",
                    "details": {"seconds": 5},
                    "reasoning": "JSON parsing failed. Waiting and will re-prompt.",
                    "message": "Waiting for 5 seconds due to API response error. Re-prompting."
                }

        except Exception as e:
            logging.error(f"❌ Error getting next action from Gemini (API error): {e}")
            return {
                "action": "WAIT",
                "details": {"seconds": 10},
                "reasoning": "Gemini API call failed. Waiting and will re-prompt.",
                "message": "Waiting for 10 seconds due to API error. Re-prompting."
            }

    def summarize_action_history(self, num_actions=5):
        """Summarize recent action history for Gemini context."""
        if not self.action_history:
            return "No actions taken yet."
        recent_actions = self.action_history[-num_actions:]
        summary = []
        for action_data in recent_actions:
            action_type = action_data['action']
            message = action_data.get('message', action_type)
            summary.append(f"Step {action_data['step']}: {message}")
        return "; ".join(summary)

    def get_recovery_action(self, screenshot, error_message, task):
        """Get a recovery action from Gemini when an action fails."""
        prompt = f"""
                There was an error during web automation.

                **Task:** {task}
                **Error Message:** {error_message}
                **Current URL:** {self.page.url}
                **Error Screenshot:** Analyze screenshot to understand error context.
                **Recent Actions:** (Summarized) {self.summarize_action_history()}

                Determine a recovery action to continue the task.

                **Recovery Action Considerations:**
                1.  Analyze screenshot and error message to understand *why* the action failed.
                2.  Is the error transient or a logical mistake?
                3.  Suggest a recovery action to resolve the issue.
                4.  Available actions: CLICK, TYPE, NAVIGATE, SCROLL, WAIT, ABORT, RETRY.

                **When to Use RETRY:** If error is temporary or due to loading, retry the *same* action after delay.

                **Explain Reasoning:** In "reasoning", explain *why* the recovery action is suggested.

                **Output Format:** JSON object:
                {{
                  "action":  (CLICK, TYPE, NAVIGATE, SCROLL, WAIT, ABORT, RETRY)
                  "details": {{ ...action-specific details... }}
                  "reasoning": "Explain recovery action."
                }}

                **If recovery is impossible, use "action": "ABORT".**

                **IMPORTANT:** Respond with JSON ONLY.
                """
        if isinstance(screenshot, bytes):
            image_bytes = screenshot
        else:
            with open(screenshot, "rb") as f:
                image_bytes = f.read()

        image_parts = [
            {
                "inline_data": {
                    "data": base64.b64encode(image_bytes).decode("utf-8"),
                    "mime_type": "image/png"
                }
            }
        ]

        try:
            response = model.generate_content([prompt] + image_parts)
            response_text = response.text.strip()

            try:
                if response_text.startswith("```json"):
                    json_text = response_text.split("```json")[1].split("```")[0].strip()
                elif response_text.startswith("```"):
                    json_text = response_text.split("```")[1].strip()
                else:
                    json_text = response_text

                recovery_action = json.loads(json_text)
                logging.info(f"🛠️ Recovery action suggested by Gemini: {recovery_action.get('reasoning', 'No reasoning provided')}")
                return recovery_action

            except (json.JSONDecodeError, IndexError) as e:
                logging.error(f"❌ Error parsing recovery action JSON: {e}")
                return {"action": "ABORT", "reasoning": "Could not parse recovery action from Gemini."}

        except Exception as e:
            logging.error(f"❌ Error getting recovery action from Gemini (API error): {e}")
            return {"action": "ABORT", "reasoning": f"API error during recovery action request: {str(e)}"}

    def execute_action(self, action_data):
        """Execute an action based on action type and details using Playwright."""
        action_type = action_data.get("action", "").upper()
        details = action_data.get("details", {})

        logging.info(f"⚙️ Executing: {action_data.get('message', action_type)}")

        try:
            if action_type == "CLICK":
                locator_str = details.get("locator", "")
                text = details.get("text", "") # Text might be used as fallback locator if locator_str is not provided or fails

                return self.click_element(locator_str=locator_str, text=text)

            elif action_type == "TYPE":
                locator_str = details.get("locator", "")
                text = details.get("text", "")
                return self.type_text(locator_str=locator_str, text=text)

            elif action_type == "NAVIGATE":
                url = details.get("url", "")
                return self.navigate_to_url(url)

            elif action_type == "SCROLL":
                direction = details.get("direction", "down")
                amount = details.get("amount", 300)
                return self.scroll_page(direction, amount)

            elif action_type == "WAIT":
                seconds = details.get("seconds", 3)
                return self.wait_for(seconds)

            elif action_type == "EXTRACT":
                extract_type = details.get("type", "text")
                locator_str = details.get("locator") # Locator for extraction
                return self.extract_content(extract_type, locator_str=locator_str)

            elif action_type == "EXPLORE_WEBSITE":
                return {"status": "SUCCESS", "message": "Website exploration action acknowledged."}

            elif action_type in ["TASK_COMPLETE", "ABORT", "MANUAL_CAPTCHA", "RETRY"]:
                return {"status": "SUCCESS", "message": "Action acknowledged"}

            else:
                return {"status": "ERROR", "message": f"Unknown action type: {action_type}"}

        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def explore_website(self, url, max_depth, current_depth=0):
        """Recursively explore a website using Playwright."""
        if current_depth >= max_depth or url in self.explored_urls:
            return

        try:
            logging.info(f"\n🌐 Exploring URL: {url}, Depth: {current_depth}")
            nav_status = self.navigate_to_url(url)
            if nav_status.get("status") == "ERROR":
                logging.error(f"❌ Error navigating to {url} during exploration: {nav_status.get('message')}")
                return

            self.explored_urls.add(url)

            self.take_screenshot()
            extract_result = self.extract_content(extract_type="text")

            if extract_result.get("status") == "SUCCESS":
                logging.info(f"📄 Extracted content from: {url} (excerpt): {extract_result['data']['text'][:150]}...")
                self.add_memory(key=urlparse(url).netloc, value=extract_result['data']['text'][:500], category="website")

            else:
                logging.warning(f"⚠️  Failed to extract content from: {url}")

            # Find all 'a' tags using Playwright locator for links
            links_locator = self.page.locator('a')
            links_count = links_locator.count() # Get count of links for iteration (more efficient than fetching all elements at once)

            urls_to_explore = set()
            base_url_parsed = urlparse(url)

            for i in range(links_count): # Iterate through links using index
                try:
                    link_element = links_locator.nth(i) # Get link element by index
                    href = link_element.get_attribute('href') # Get href attribute using Playwright
                    absolute_url = urljoin(url, href)

                    if absolute_url and absolute_url.startswith(('http://', 'https://')):
                        url_parsed = urlparse(absolute_url)
                        if url_parsed.netloc == base_url_parsed.netloc and absolute_url not in self.explored_urls:
                            urls_to_explore.add(absolute_url)

                except Exception as e: # Catch any issues during link processing
                    logging.warning(f"Issue processing link during exploration: {e}")
                    continue

            for next_url in urls_to_explore:
                self.explore_website(next_url, max_depth, current_depth + 1)

        except Exception as e:
            logging.error(f"🔥 Error during website exploration of {url}: {e}")

    def find_element_by_locator(self, locator_str, text=None, index=0):
        """Find an element using Playwright locator or fallback to text if locator fails."""
        start_time = time.time()

        while time.time() - start_time < self.element_search_timeout:
            try:
                if locator_str:
                    locator = self.page.locator(locator_str) # Use Playwright locator directly
                    count = locator.count() # Check if elements are found

                    if count > 0:
                        if 0 <= index < count:
                            element_locator = locator.nth(index) # Get specific element if index is within range
                        else:
                            element_locator = locator.first # Default to the first element if index is out of range

                        if self.debug:
                            element_locator.evaluate("element => { element.style.border = '3px solid red'; }") # Highlight element
                            time.sleep(0.5)
                        return element_locator # Return Playwright Locator object

                if text: # Fallback to text based search if locator_str is not provided or initial locator didn't find element
                    # Playwright Text Locators are very powerful and should be preferred.
                    text_locator_strategies = [
                        f"text={text}", # Exact text match
                        f"text={text}>>nth={index}", # Exact text match with index
                        f"text=regexp:^{text}$", # Exact text match using regex
                        f"text=*{text}", # Contains text
                        f"text=regexp:{text}", # Contains text using regex
                        f"text=iregex:{text}", # Contains text, case-insensitive regex
                        f"text='{text}'", # Exact text with single quotes
                        f"text=\"{text}\"", # Exact text with double quotes
                        f"text=localized:\"{text}\"" # Localized text (if applicable)
                    ]
                    for strategy in text_locator_strategies:
                        locator = self.page.locator(strategy)
                        count = locator.count()
                        if count > 0:
                            if 0 <= index < count:
                                element_locator = locator.nth(index)
                            else:
                                element_locator = locator.first

                            if self.debug:
                                element_locator.evaluate("element => { element.style.border = '3px solid blue'; }")
                                time.sleep(0.5)
                            return element_locator # Return Playwright Locator object

            except Exception as e:
                logging.warning(f"Error finding element with locator '{locator_str}' or text '{text}': {e}. Retrying...")
                pass # Retry

        return None # Element not found

    def click_element(self, locator_str=None, text=None, index=0):
        """Click on an element using Playwright locator or text. Demonstrates various click options."""
        try:
            logging.info(f"🖱️ Clicking: {text if text else locator_str}")
            element_locator = self.find_element_by_locator(locator_str, text, index)

            if element_locator:

                # --- Playwright Click Actions and Options ---
                # 1. Basic Click:
                # element_locator.click()

                # 2. Force Click (Bypasses visibility checks - use cautiously):
                # element_locator.click(force=True)

                # 3. Positioned Click (Click at specific coordinates within the element):
                # bounding_box = element_locator.bounding_box()
                # if bounding_box:
                #     x = bounding_box['x'] + bounding_box['width'] / 2 # Center X
                #     y = bounding_box['y'] + bounding_box['height'] / 2 # Center Y
                #     self.page.mouse.click(x, y)
                # else:
                #     element_locator.click() # Fallback if bounding box fails

                # 4. Click with Delay (Simulate user-like click):
                # element_locator.click(delay=100) # 100ms delay

                # 5. No Wait After (For faster navigation in some cases - use with care):
                # element_locator.click(no_wait_after=True)

                # 6. Timeout for Click (Control how long to wait for element to be actionable):
                # element_locator.click(timeout=5000) # 5 seconds timeout

                # 7. Multiple Clicks (Double click, Triple click etc.):
                # element_locator.click(click_count=2) # Double click

                # Using a standard click for now for general use case:
                element_locator.click()

                # --- Waiting after Click ---
                # 1. Wait for Load State (Most common for page navigation):
                self.page.wait_for_load_state("load") # "load", "domcontentloaded", "networkidle"

                # 2. Wait for Navigation (Specifically for navigation actions):
                # self.page.wait_for_navigation() # Waits until navigation completes

                # 3. Wait for Selector (Wait for an element to appear after click):
                # self.page.wait_for_selector(".next-page-content")

                # 4. Explicit Timeout (If specific wait is needed):
                # time.sleep(2) # Wait for 2 seconds

                if self.debug:
                    self.take_screenshot()

                return {
                    "status": "SUCCESS",
                    "message": f"Clicked on element with locator: '{locator_str}' or text: '{text}'",
                    "title": self.page.title(),
                    "current_url": self.page.url
                }
            else:
                return {"status": "ERROR", "message": f"Element not found for click: locator='{locator_str}', text='{text}'"}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def type_text(self, locator_str=None, text=None):
        """Type text into an input element using Playwright. Demonstrates various typing methods."""
        if not text:
            return {"status": "ERROR", "message": "No text provided to type"}

        try:
            logging.info(f"⌨️ Typing: {text}")

            element_locator = None
            if locator_str:
                element_locator = self.find_element_by_locator(locator_str)

            if not element_locator:
                # Fallback to find any input, textarea, or editable element if locator fails
                input_locators = [
                    "input", "textarea", "[contenteditable='true']", "[role='textbox']"
                ]
                for sel in input_locators:
                    temp_locator = self.page.locator(sel)
                    if temp_locator.count() > 0:
                        element_locator = temp_locator.first # Take the first one if multiple are found
                        break

            if element_locator:
                # --- Playwright Typing Actions and Options ---
                # 1. Fill (Recommended for input fields - clears existing content and types):
                # element_locator.fill(text)

                # 2. Type (Simulates keyboard typing - appends to existing content, can use delay):
                # element_locator.type(text) # Basic type
                # element_locator.type(text, delay=50) # Type with 50ms delay per character

                # 3. Press Sequences (Send special keys, combinations):
                # element_locator.press("Enter")
                # element_locator.press("Shift+Tab")
                # element_locator.pressSequentially(text, delay=50) # Type with delay, like .type but can handle special characters better

                # 4. Clear and Type (Manual clear before typing):
                # element_locator.clear() # Playwright's clear is robust
                # element_locator.type(text)

                # Using fill for robustness in most input scenarios:
                element_locator.fill(text)

                return {"status": "SUCCESS", "message": f"Typed '{text}' into input field using locator: '{locator_str}'"}
            else:
                # Fallback to typing into focused element if no specific input is found
                self.page.keyboard.type(text) # Type into currently focused element
                return {"status": "SUCCESS", "message": f"Typed '{text}' into active element (fallback)"}

        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def navigate_to_url(self, url):
        """Navigate to a specific URL using Playwright."""
        if not url:
            return {"status": "ERROR", "message": "No URL provided"}

        try:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            logging.info(f"🌐 Navigating to: {url}")
            self.page.goto(url, wait_until="load", timeout=30000) # Playwright's goto with wait_until and timeout

            self.handle_dialogs() # Handle dialogs after navigation

            if self.debug:
                self.take_screenshot()

            return {
                "status": "SUCCESS",
                "message": f"Navigated to {url}",
                "title": self.page.title(),
                "current_url": self.page.url
            }
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def scroll_page(self, direction="down", amount=300):
        """Scroll the page using Playwright. Demonstrates different scroll options."""
        try:
            logging.info(f"📜 Scrolling {direction}")

            # --- Playwright Scrolling Options ---
            # 1. JavaScript Scroll (Similar to Selenium, but using Playwright's evaluate):
            if direction.lower() == "down":
                self.page.evaluate(f"window.scrollBy(0, {amount})")
            elif direction.lower() == "up":
                self.page.evaluate(f"window.scrollBy(0, -{amount})")
            elif direction.lower() == "top":
                self.page.evaluate("window.scrollTo(0, 0)")
            elif direction.lower() == "bottom":
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            elif direction.lower() == "right":
                self.page.evaluate(f"window.scrollBy({amount}, 0)")
            elif direction.lower() == "left":
                self.page.evaluate(f"window.scrollBy(-{amount}, 0)")

            # 2. Playwright's built-in scrolling (More control over element scrolling - for specific elements, not whole page directly)
            # For whole page scrolling, JavaScript approach is still common and effective.

            time.sleep(1)

            if self.debug:
                self.take_screenshot()

            return {"status": "SUCCESS", "message": f"Scrolled {direction}"}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def wait_for(self, seconds=3):
        """Wait for the specified number of seconds using Playwright."""
        try:
            logging.info(f"⏱️ Waiting for {seconds} seconds")
            self.page.wait_for_timeout(seconds * 1000) # Playwright's wait_for_timeout takes milliseconds
            return {"status": "SUCCESS", "message": f"Waited for {seconds} seconds"}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def extract_content(self, extract_type="text", locator_str=None):
        """Extract content from the page using Playwright. Demonstrates various extraction methods."""
        try:
            logging.info(f"📄 Extracting {extract_type} content")

            if extract_type == "text":
                # Extract main text content, optionally using a locator

                if locator_str:
                    element_locator = self.find_element_by_locator(locator_str=locator_str)
                    if element_locator:
                        # --- Playwright Text Extraction Methods ---
                        # 1. textContent() - Get text content of the element and its children
                        text_content = element_locator.text_content()

                        # 2. innerText() - Get rendered text content (similar to browser's innerText property)
                        # text_content = element_locator.inner_text()

                        # 3. innerHTML() - Get the inner HTML content of the element
                        # html_content = element_locator.inner_html()
                        # text_content = html_content # Or process HTML as needed

                        # 4. getAttribute() - Get specific attribute value
                        # attribute_value = element_locator.get_attribute("href")
                        # text_content = attribute_value # Or process attribute value

                    else:
                        return {"status": "ERROR", "message": f"Could not find element with locator: {locator_str}"}
                else:
                    # Extract from whole body if no locator specified
                    text_content = self.page.locator("body").text_content() # Extract text from body

                main_text = text_content[:2000] + "..." if len(text_content) > 2000 else text_content

                return {
                    "status": "SUCCESS",
                    "message": f"Extracted text content",
                    "data": {
                        "title": self.page.title(),
                        "url": self.page.url,
                        "text": main_text
                    }
                }

            elif extract_type == "links":
                # Extract links
                links = []
                link_elements_locator = self.page.locator("a") # Locator for all 'a' tags
                link_count = link_elements_locator.count() # Get count of links for iteration

                for i in range(min(link_count, 20)): # Limit to first 20 links
                    try:
                        link_element = link_elements_locator.nth(i)
                        href = link_element.get_attribute("href") # Get 'href' attribute
                        text = link_element.text_content().strip() # Get link text

                        if href and text and len(text) > 1:
                            links.append({"url": href, "text": text})
                    except:
                        continue

                return {
                    "status": "SUCCESS",
                    "message": f"Extracted {len(links)} links",
                    "data": {
                        "title": self.page.title(),
                        "url": self.page.url,
                        "links": links
                    }
                }

            elif extract_type == "search_results":
                # Extract search results (Google Search example)
                results = []
                search_result_selectors = [
                    "div.g", "div[data-sokoban-container]", "div.v7W49e" # Common Google search result containers
                ]

                for selector in search_result_selectors:
                    result_elements_locator = self.page.locator(selector)
                    result_count = result_elements_locator.count()

                    if result_count > 0:
                        for i in range(min(result_count, 10)): # Limit to first 10 results
                            try:
                                result_element = result_elements_locator.nth(i)

                                # --- Chained Locators for deeper element selection ---
                                title_locator = result_element.locator("h3") # Find h3 within result
                                title = title_locator.text_content()

                                link_locator = title_locator.locator("xpath=./ancestor::a") # Find parent 'a' tag using XPath relative to title
                                link = link_locator.get_attribute("href")

                                desc_locator = result_element.locator("div.VwiC3b, div.s") # Find description
                                description = desc_locator.text_content() if desc_locator.count() > 0 else "" # Optional description

                                results.append({
                                    "title": title,
                                    "url": link,
                                    "description": description
                                })
                            except:
                                continue
                        if results:
                            break # Stop if results are found for a selector

                return {
                    "status": "SUCCESS",
                    "message": f"Extracted {len(results)} search results",
                    "data": {
                        "query": self.page.title().replace(" - Google Search", ""),
                        "url": self.page.url,
                        "results": results
                    }
                }
            elif extract_type == "element_text" and locator_str: # Extract text from a specific element using locator
                 element_locator = self.find_element_by_locator(locator_str=locator_str)
                 if element_locator:
                     return {
                         "status": "SUCCESS",
                         "message": f"Extracted text from element with locator '{locator_str}'",
                         "data": {
                             "text": element_locator.text_content(),
                             "url": self.page.url
                         }
                     }
                 else:
                     return {"status": "ERROR", "message": f"Element with locator '{locator_str}' not found for extraction."}

            else:
                return {"status": "ERROR", "message": f"Unknown extract type: {extract_type}"}

        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def handle_dialogs(self):
        """Handle common dialogs like cookie notices and popups using Playwright."""
        dismiss_selectors = [
            "#L2AGLb",  # Google cookie notice
            "button[aria-label='Accept all']",
            "button[aria-label='Accept']",
            "text=Accept", # Text based locator example
            "text=Accept all",
            "text=I agree",
            "text=Agree",
            "text=Allow",
            "text=Close",
            "text=No thanks",
            "text=Got it",
            ".modal button",
            ".popup button",
            "[aria-label='Close']",
            ".cookie-banner button",
            "#consent-banner button",
            ".consent button"
        ]

        for selector in dismiss_selectors:
            try:
                dialog_locator = self.page.locator(selector)
                if dialog_locator.count() > 0: # Check if dialog element exists
                    if dialog_locator.is_visible(): # Check for visibility to ensure it's actually displayed
                        dialog_locator.click(timeout=5000) # Click to dismiss, with a timeout
                        logging.info(f"🍪 Dismissed dialog with selector: {selector}")
                        break # Dismiss only one dialog at a time per handle_dialogs call
            except Exception as e:
                logging.warning(f"Issue handling dialog with selector '{selector}': {e}")
                continue

    def generate_task_summary(self, task):
        """Generate a summary of the task execution."""
        successful_steps = sum(
            1 for action in self.action_history if action.get('action') not in ['TASK_COMPLETE', 'ABORT', 'MANUAL_CAPTCHA',
                                                                               'RETRY',
                                                                               'EXPLORE_WEBSITE'] and action.get(
                'status') == 'SUCCESS')
        error_steps = sum(1 for action in self.action_history if action.get('status') == 'ERROR')
        manual_captcha_steps = sum(1 for action in self.action_history if action.get('action') == 'MANUAL_CAPTCHA')
        exploration_steps = sum(1 for action in self.action_history if action.get('action') == 'EXPLORE_WEBSITE')

        final_screenshot, _ = self.take_screenshot()

        summary = [
            f"Task: {task}",
            f"Completed {successful_steps} action(s) with {error_steps} error(s) encountered.",
            f"Manual Captcha Handled: {manual_captcha_steps} time(s).",
            f"Website Exploration Steps: {exploration_steps} initiated.",
            f"Final URL: {self.page.url}",
            f"Final page title: {self.page.title()}"
        ]

        if exploration_steps > 0:
            summary.append("Note: Website exploration was performed.")

        try:
            extract_result = self.extract_content("text")
            if extract_result.get("status") == "SUCCESS":
                summary.append(f"Page content (excerpt): {extract_result['data']['text'][:200]}...")
        except:
            pass

        return "\n".join(summary)

def run_assistant():
    """Main function to run the autonomous web assistant."""
    parser = argparse.ArgumentParser(description="Autonomous Web Assistant powered by Gemini and Playwright")
    parser.add_argument("task", nargs="?", help="The task to perform")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode (no browser UI)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode with more screenshots and logging")
    parser.add_argument("--memory_file", default="memory.json", help="Path to the memory file (JSON format).")
    args = parser.parse_args()

    assistant = AutonomousWebAssistant(headless=args.headless, debug=args.debug, memory_file=args.memory_file)

    try:
        if args.task:
            assistant.execute_task(args.task)
        else:
            print("🤖 Autonomous Web Assistant powered by Gemini and Playwright")
            print("Type 'exit' or 'quit' to end, 'clear memory' to clear, or 'show memory' to display memory.")

            while True:
                task = input("Enter a task (or command): ")
                if task.lower() in ['exit', 'quit']:
                    break
                elif task.lower() == 'clear memory':
                    category = input("Clear all memory or specific category? (all/[category_name]): ").strip()
                    if category.lower() == 'all':
                         assistant.clear_memory()
                    else:
                        assistant.clear_memory(category=category)
                    print("Memory cleared.")
                elif task.lower() == 'show memory':
                    print(json.dumps(assistant.memory, indent=4))
                else:
                    assistant.execute_task(task)
    finally:
        assistant.close_browser()

if __name__ == "__main__":
    run_assistant()
