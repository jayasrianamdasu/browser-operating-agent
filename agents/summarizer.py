import logging
from utils.llm_client import call_llm

logger = logging.getLogger("browser_agent.summarizer")

class SummarizerAgent:
    def __init__(self, api_key: str = None, model: str = None, use_mock: bool = True):
        self.api_key = api_key
        self.model = model
        self.use_mock = use_mock

    def get_system_prompt(self) -> str:
        return (
            "You are the Summarizer Agent of a Browser Operating Agent system. Your job is to take the user's original "
            "task request and the raw information extracted during web interactions, and synthesize them into a final, "
            "polished, high-quality markdown response.\n"
            "Format the summary professionally using headers, subheaders, lists, tables, and bold highlights. "
            "Ensure all links extracted are formatted as clickable markdown links. Avoid phrases like 'based on the "
            "provided data'. Present the findings directly as an expert assistant answering the user."
        )

    def summarize(self, task: str, extracted_data: str) -> str:
        """
        Synthesizes the extracted data into a final markdown answer answering the user's task.
        """
        logger.info(f"Summarizing results for task: '{task}'")
        
        prompt = (
            f"Original Task: {task}\n\n"
            f"--- EXTRACTED INFORMATION FROM BROWSER ---\n"
            f"{extracted_data}\n"
            f"--- END EXTRACTED INFORMATION ---\n"
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
            logger.info("Summary generated successfully.")
            return response.strip()
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return f"Error generating summary: {str(e)}"
