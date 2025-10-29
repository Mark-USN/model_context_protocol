# prompt_functions.py


import logging
from pathlib import Path
from typing import TypeVar, List, Dict
from fastmcp import FastMCP
from fastmcp.prompts.prompt import Message, PromptMessage, TextContent, PromptResult
from pydantic import Field

T = TypeVar("T", bound=FastMCP)


logger = logging.getLogger(f"{Path(__file__).stem}")



# Basic prompt returning a string (converted to user message automatically)
def ask_about_topic(topic: str) -> str:
    """Generates a user message asking for an explanation of a topic."""
    return f"Can you please explain the concept of '{topic}'?"

# Prompt returning a specific message type
def generate_code_request(language: str, task_description: str) -> PromptMessage:
    """Generates a user message requesting code generation."""
    content = f"Write a {language} function that performs the following task: {task_description}"
    return PromptMessage(role="user", content=TextContent(type="text", text=content))

def data_analysis_prompt(
    data_uri: str = Field(description="The URI of the resource containing the data."),
    analysis_type: str = Field(default="summary", description="Type of analysis.")
) -> str:
    """Creates a request to analyze data with specific parameters."""
    return f"Please perform a '{analysis_type}' analysis on the data found at {data_uri}."

def analyze_data(numbers: List[int], metadata: Dict[str, str], threshold: float) -> str:
    """Analyze numerical data."""
    avg = sum(numbers) / len(numbers)
    return f"Average: {avg}, above threshold: {avg > threshold}"

def roleplay_scenario(character: str, situation: str) -> PromptResult:
    """Sets up a roleplaying scenario with initial messages."""
    return [
        Message(f"Let's roleplay. You are {character}. The situation is: {situation}"),
        Message("Okay, I understand. I am ready. What happens next?", role="assistant")
    ]

def data_analysis_prompt_chart_op(data_uri: str, analysis_type: str = "summary", include_charts: bool = False) -> str:
    """Creates a request to analyze data with specific parameters and optional chart request."""
    prompt = f"Please perform a '{analysis_type}' analysis on the data found at {data_uri}."
    if include_charts:
        prompt += " Include relevant charts and visualizations."
    return prompt

def register(mcp: T):
    """Register prompts with MCPServer."""
    logger.info("Registering prompts")
    mcp.prompt(tags=["public", "api"])(ask_about_topic)
    mcp.prompt(tags=["public", "api"])(generate_code_request)
    mcp.prompt(tags=["public", "api"])(data_analysis_prompt)
    mcp.prompt(tags=["public", "api"])(roleplay_scenario)
    mcp.prompt(tags=["public", "api"])(data_analysis_prompt_chart_op)

