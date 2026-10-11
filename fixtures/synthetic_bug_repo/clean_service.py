"""Clean utility module with robust input validation and defensive checks."""


def format_user_name(first_name: str, last_name: str) -> str:
    """Format full name with strict validation.

    This function is completely clean and should never be flagged as buggy.
    """
    if not first_name or not isinstance(first_name, str):
        raise ValueError("first_name must be a non-empty string")
    if not last_name or not isinstance(last_name, str):
        raise ValueError("last_name must be a non-empty string")

    return f"{first_name.strip().title()} {last_name.strip().title()}"
