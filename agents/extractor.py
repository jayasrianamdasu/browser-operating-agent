import logging
from utils.llm_client import call_llm
from utils.helpers import clean_html

logger = logging.getLogger("browser_agent.extractor")

class ExtractorAgent:
    def __init__(self, api_key: str = None, model: str = None, use_mock: bool = True):
        self.api_key = api_key
        self.model = model
        self.use_mock = use_mock

    def get_system_prompt(self) -> str:
        return (
            "You are the Extractor Agent of a Browser Operating Agent system. Your job is to extract structured, "
            "relevant information from the provided text content of a webpage based on the user's extraction target.\n"
            "Focus ONLY on the information requested. Extract items, titles, links, prices, dates, or summaries "
            "as specified by the target. Format your output as a clean bulleted list or markdown table. "
            "Do not include conversational filler, meta-explanations, or intros. Return only the extracted data."
        )

    def extract(self, html_content: str, target: str, url: str = "") -> str:
        """
        Cleans HTML content and calls the LLM to extract targeted info.
        """
        logger.info(f"Extracting information for target: '{target}' on page: {url}")
        
        # Clean HTML first to save tokens and fit context
        cleaned_text = clean_html(html_content, page_url=url)
        
        prompt = (
            f"Source URL: {url}\n"
            f"Extraction Target: {target}\n\n"
            f"--- WEBPAGE TEXT CONTENT ---\n"
            f"{cleaned_text}\n"
            f"--- END WEBPAGE TEXT CONTENT ---\n"
        )
        
        try:
            response = call_llm(
                prompt=prompt,
                system_prompt=self.get_system_prompt(),
                json_mode=False,
                api_key=self.api_key,
                model=self.model,
                use_mock=self.use_mock
            )
            logger.info("Extraction completed successfully.")
            return response.strip()
        except Exception as e:
            logger.error(f"Failed to extract information: {e}")
            return f"Error extracting content: {str(e)}"
