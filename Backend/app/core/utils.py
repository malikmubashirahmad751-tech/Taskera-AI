def is_questioning_response(response: str) -> bool:
    """
    Checks if an agent's response is a question or a request for more information.
    """
    if not response:
        return False
        
    text = response.strip().lower()

    if text.endswith('?'):
        return True

    question_starters = [
        "what", "who", "when", "where", "why", "how",
        "do you", "can you", "could you", "would you",
        "is there", "are there", "should i", "tell me more, Please"
    ]
    if any(text.startswith(starter) for starter in question_starters):
        return True

    return False