# 🌐🤖 WebSurferAI: Your Autonomous Web Navigator

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)](https://example.com) <!-- Replace with your actual build status badge if you have one -->
[![Python Version](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) <!-- Add a LICENSE file to your repo, e.g., MIT -->


**WebSurferAI** is a cutting-edge autonomous web assistant that leverages the power of Google's Gemini Pro Vision API and Playwright to interact with websites like a human.  It can understand complex tasks, navigate web pages, fill forms, extract information, and even handle CAPTCHAs (with your help!).  This project is in active development, and we're looking for passionate contributors to make it even more amazing! 🚀✨

## 🌟 Features

*   **Autonomous Task Execution:**  Give it a task, and it will try its best to complete it.
*   **Intelligent Navigation:**  Uses Gemini Pro Vision to understand web pages and decide the best course of action.
*   **Dynamic Interaction:** Clicks buttons, fills forms, scrolls pages, and more.
*   **Information Extraction:**  Pulls relevant text and data from websites.
*   **Memory System:** Remembers past interactions and learns from them (stores in `memory.json`).
*   **CAPTCHA Handling:**  Detects CAPTCHAs and prompts you for manual assistance.
*   **Website Exploration Mode:**  Can explore websites to discover functionalities, especially useful for initial task discovery.
*   **Error Recovery:** Attempts to recover from errors and continue the task.
*   **Debug Mode:**  Provides detailed logging and saves screenshots for each step.
*   **Internal Monologue:**  Logs Gemini's reasoning and decision-making process (in debug mode).
* **Handles dialogs**

## 🚀 Getting Started

### Prerequisites

1.  **Python:**  Make sure you have Python 3.7 or higher installed.  You can check by running `python --version` or `python3 --version` in your terminal.
2.  **Playwright:**  The project uses Playwright for browser automation.  It will be installed in the next step, but you'll need the browser binaries.
3.  **Google Gemini API Key:** You'll need an API key for Google Gemini. You can get one from [Google AI Studio](https://makersuite.google.com/app/apikey).
4. **Node.js and npm (or yarn)**: Playwright uses Node.js. Install Node.js and npm.

### Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/yourusername/WebSurferAI.git  # Replace with your repo URL
    cd WebSurferAI
    ```

2.  **Create a virtual environment (recommended):**

    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```
    Create a `requirements.txt` file with these contents:
    ```
    playwright
    Pillow
    python-dotenv
    google-generativeai
    ```

4.  **Install Playwright browsers:**

    ```bash
    playwright install
    ```
    This command downloads the necessary browser binaries (Chromium, Firefox, WebKit).  This might take a few minutes.

5.  **Set up your API Key:**

    *   Create a `.env` file in the root directory of the project.
    *   Add your Gemini API key to the `.env` file:

        ```
        GEMINI_API_KEY=your_api_key_here
        ```
    *   **Important:**  *Never* commit your `.env` file to version control.  Add `.env` to your `.gitignore` file.

### Running the Assistant

1.  **From the command line:**

    ```bash
    python main.py "Your task here"
    ```
     Replace `"Your task here"` with the task you want the assistant to perform.  For example:

    ```bash
    python main.py "Find the price of a Tesla Model 3 on the Tesla website"
    ```

    *   **Headless mode:** To run without showing the browser window, use the `--headless` flag:

        ```bash
        python main.py "Your task here" --headless
        ```

    *   **Debug mode:** For more detailed output and screenshots, use the `--debug` flag:

        ```bash
        python main.py "Your task here" --debug
        ```
    *   **Specify memory file (optional):** Use --memory_file, defaults to `memory.json`

        ```bash
        python main.py "Your task here" --memory_file my_custom_memory.json
        ```

2.  **Interactive Mode:** If you run the script without a task argument, it will start in interactive mode:

    ```bash
    python main.py
    ```

    You can then enter tasks one by one.  You can also use the following commands:
    *   `exit` or `quit`:  End the program.
    *   `clear memory`:  Clears the assistant's memory.  You can also specify a category: `clear memory website`.
    *   `show memory`: Displays the current contents of the memory.

## 🤝 Contributing

We ❤️ contributions!  WebSurferAI is a community project, and we welcome anyone who wants to help make it better. Whether you're a seasoned developer or just starting out, there are many ways to contribute:

*   **Bug Reports:** If you find a bug, please open an issue on GitHub.  Be as detailed as possible, including steps to reproduce the bug.
*   **Feature Requests:**  Have an idea for a new feature?  Open an issue and describe it!
*   **Code Contributions:**
    *   Fork the repository.
    *   Create a new branch for your feature or bug fix: `git checkout -b my-new-feature`
    *   Make your changes.
    *   Write tests for your code (if applicable).
    *   Ensure your code follows the existing style (use a linter like `flake8` or `pylint`).
    *   Commit your changes: `git commit -m "Add some amazing feature"`
    *   Push to your branch: `git push origin my-new-feature`
    *   Open a pull request on GitHub.
*   **Documentation:**  Improve the README, add docstrings to the code, or create tutorials.
*   **Testing:** Help us test the assistant on different websites and with different tasks.
*   **Ideas and Feedback:** Share your thoughts and suggestions on how to improve the project.

We especially need help with:

*   **Improving the prompt engineering:** Refining the prompts sent to Gemini can significantly enhance the assistant's performance.
*   **Expanding error handling:**  Making the assistant more robust to unexpected website behavior.
*   **Adding support for more websites:**  Testing and adapting the assistant to work with a wider range of websites.
*   **Developing a user interface:**  A graphical user interface would make the assistant more accessible.
*   **Creating more sophisticated memory management:**  Improving how the assistant stores and retrieves information.
* **Parallel task execution:** allowing for multiple simultaneous actions, if possible.

## 🗺️ Project Structure

*   `main.py`:  The main script containing the `AutonomousWebAssistant` class and the command-line interface.
*   `screenshots/`:  Directory where screenshots are saved (created automatically).
*   `memory.json`:  The default file where the assistant's memory is stored (created automatically).
*   `.env`:  File for storing your API key (you need to create this).
* `requirements.txt`: List of Python dependencies.

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. (You need to create a LICENSE file).

## 🙏 Acknowledgements

*   Google Gemini Team
*   Playwright Team
*   All the contributors!

Let's build the future of web automation together! 🌐✨🤖
