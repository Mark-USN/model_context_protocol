# tools/math_tools.py
from ..registry import tool

@tool(description="Add two numbers.")
def add(a: str, b: str) -> str:
    """Add two numbers (strings ok); returns string."""
    return str(float(a) + float(b))

@tool(name="mul", description="Multiply two numbers.")
def multiply(a: str, b: str) -> str:
    return str(float(a) * float(b))

