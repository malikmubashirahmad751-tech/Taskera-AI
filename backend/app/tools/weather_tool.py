import os
from langchain.tools import StructuredTool
from langchain_community.utilities import OpenWeatherMapAPIWrapper
from app.core.session_manager import user_sessions, get_user_memory

openweathermap_api_key = os.getenv("YOUR_OPENWEATHERMAP_API_KEY")


weather_wrapper = OpenWeatherMapAPIWrapper(openweathermap_api_key=openweathermap_api_key)


def weather_search(location: str = "") -> str:
    """
    Get the current weather for a city.
    If no city or an invalid placeholder like 'current' is provided, ask the user for it.
    """
    if not location or location.strip().lower() in ["", "current", "none"]:
        return "Can you provide a valid city name to check the weather (e.g., 'Karachi' or 'London, UK')."

    try:
        return weather_wrapper.run(location)
    except Exception as e:
        return f"Sorry, I couldn’t fetch the weather for '{location}'. Please check the city name and try again."


weather_tool = StructuredTool.from_function(
    func=weather_search,
    name="weather_search",
    description="Get current weather for a given city and country code, e.g., 'London, UK'. If city not provided, it asks for one."
)
