# prompt_functions.py


import logging
from pathlib import Path
from typing import TypeVar, List, Dict
from fastmcp import FastMCP
from fastmcp.prompts.prompt import Message, PromptMessage, TextContent, PromptResult
from pydantic import Field

T = TypeVar("T", bound=FastMCP)

# -----------------------------
# Logging setup
# -----------------------------
logging.basicConfig(
    # level=logging.DEBUG if settings.debug else logging.INFO,
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(Path(__file__).stem)




# Basic prompt returning a string (converted to user message automatically)
def ask_about_topic(topic: str) -> str:
    """Generates a user message asking for an explanation of a topic.
        Args:
            topic (str): The topic to be explained.
        Returns:
            str: The generated prompt message.
    """
    return f"Can you please explain the concept of '{topic}'?"

# Prompt returning a specific message type
def generate_code_request(language: str, task_description: str) -> PromptMessage:
    """Generates a user message requesting code generation.
        Args:
            language (str): The programming language for the code.
            task_description (str): Description of the task to be performed.
        Returns:
            PromptMessage: The generated prompt message to create the desired code in 
                            the specified language.
    """
    content = f"Write a {language} function that performs the following task: {task_description}"
    return PromptMessage(role="user", content=TextContent(type="text", text=content))

def data_analysis_prompt(
    data_uri: str = Field(description="The URI of the resource containing the data."),
    analysis_type: str = Field(default="summary", description="Type of analysis.")
) -> str:
    """Creates a request to analyze data with specific parameters.
        Args:
            data_uri (str): The URI of the resource containing the data.
            analysis_type (str): Type of analysis to be performed.
        Returns:
            str: The generated prompt message requesting data analysis.
    """
    return f"Please perform a '{analysis_type}' analysis on the data found at {data_uri}."

def analyze_data(numbers: List[int], metadata: Dict[str, str], threshold: float) -> str:
    """Analyze numerical data.
        Args:
            numbers (List[int]): List of numbers to analyze.
            metadata (Dict[str, str]): Additional metadata for context.
            threshold (float): Threshold value for analysis.
        Returns:
            str: Analysis result.
    """
    avg = sum(numbers) / len(numbers)
    return f"Average: {avg}, above threshold: {avg > threshold}"

def roleplay_scenario(character: str, situation: str) -> PromptResult:
    """Sets up a roleplaying scenario with initial messages.
        Args:
            character (str): The character to roleplay as.
            situation (str): The situation to roleplay in.
        Returns:
            PromptResult: The initial messages for the roleplaying scenario.
    """
    return [
        Message(f"Let's roleplay. You are {character}. The situation is: {situation}"),
        Message("Okay, I understand. I am ready. What happens next?", role="assistant")
    ]

def data_analysis_prompt_chart_op(
    data_uri: str, 
    analysis_type: str = "summary", 
    include_charts: bool = False) -> str:
    """Creates a request to analyze data with specific parameters and optional chart request.
        Args:
            data_uri (str): The URI of the resource containing the data.
            analysis_type (str): Type of analysis to be performed.
            include_charts (bool): Whether to include charts in the analysis.
        Returns:
            str: The generated prompt message requesting data analysis with optional charts.
    """
    prompt = f"Please perform a '{analysis_type}' analysis on the data found at {data_uri}."
    if include_charts:
        prompt += " Include relevant charts and visualizations."
    return prompt

def register(mcp: T):
    """Register prompts with MCPServer.
        Args:
            mcp (T): The MCP server instance.
    """
    logger.info("Registering prompts")
    mcp.prompt(tags=["public", "api"])(ask_about_topic)
    mcp.prompt(tags=["public", "api"])(generate_code_request)
    mcp.prompt(tags=["public", "api"])(data_analysis_prompt)
    mcp.prompt(tags=["public", "api"])(roleplay_scenario)
    mcp.prompt(tags=["public", "api"])(data_analysis_prompt_chart_op)

