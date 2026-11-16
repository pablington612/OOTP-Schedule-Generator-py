def read_line(prompt):
    """Prompt and read one line; None at end of input."""
    try:
        return input(prompt)
    except EOFError:
        return None
