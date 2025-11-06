from langchain_core.tools import StructuredTool

def calculator_tool_function(expression: str) -> str:
    """Evaluates basic mathematical expressions safely."""
    try:
        
        allowed = "0123456789+-*/(). "
        if not all(c in allowed for c in expression):
            return "Invalid characters in expression."
        result = eval(expression)
        return f"The result of '{expression}' is {result}"
    except Exception as e:
        return f"Error evaluating expression: {e}"

calculator_tool = StructuredTool.from_function(
    name="calculator_tool",
    func=calculator_tool_function,
    description="Performs basic arithmetic calculations like addition, subtraction, multiplication, and division."
)
