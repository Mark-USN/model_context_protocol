from types import TypeVar

from fastmcp import FastMCP

T = TypeVar("T": bound=FastMCP)

def data_analysis_prompt(
    data_uri: str = Field(description="The URI of the resource containing the data."),
    analysis_type: str = Field(default="summary", description="Type of analysis.")
) -> str:
    """Creates a request to analyze data with specific parameters."""
    return f"Please perform a '{analysis_type}' analysis on the data found at {data_uri}."

def register(mcp: T):
    mcp.prompt(
        name="analyze_data_request",          # Custom prompt name
        description="Creates a request to analyze data with specific parameters",  # Custom description
        tags={"public", "analysis", "data"},            # Optional categorization tags
        meta={"version": "1.1", "author": "data-team"}  # Custom metadata
    )(data_analysis_prompt)